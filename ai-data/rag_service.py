"""
RAG Service for AI Tutor System
Handles document loading, chunking, embedding, and retrieval

Task 2: Vector Database Setup (Migrated to Qdrant)
- 2.2: Configure Qdrant client with error handling
- 2.3: Create collection for K8s docs with proper settings
- 2.5: Add comprehensive error handling
"""

import os
import hashlib
import time
import uuid
from typing import List, Dict, Optional
from dataclasses import dataclass
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    PointIdsList,
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document
from config import AISettings, config

# 임베딩 차원: OpenAI text-embedding-ada-002=1536, Gemini gemini-embedding-001=3072
_EMBEDDING_DIMENSIONS = {
    "openai": 1536,
    "gemini": 3072,
    "mock": 1536,
}
SUPPORTED_ENVIRONMENTS = frozenset({"kubernetes", "docker", "linux"})


class _OfflineEmbeddings:
    """API key와 network 없이 사용하는 결정적 sparse embedding."""

    def __init__(self, dimension: int):
        self.dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


@dataclass
class RetrievedDocument:
    """Retrieved document with metadata"""
    content: str
    similarity: float
    source: str
    metadata: Dict


@dataclass(frozen=True)
class IngestionReport:
    """멱등 동기화 결과."""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.added + self.updated + self.unchanged


class RAGServiceError(Exception):
    """Base exception for RAG service errors"""
    pass


class QdrantConnectionError(RAGServiceError):
    """Qdrant connection error"""
    pass


class DocumentIngestionError(RAGServiceError):
    """Document ingestion error"""
    pass


class SearchError(RAGServiceError):
    """Search error"""
    pass


class RAGService:
    """
    Retrieval-Augmented Generation service
    Handles vector storage and semantic search using Qdrant
    
    Task 2 Implementation:
    - 2.2: Qdrant client with config integration
    - 2.3: K8s docs collection with metadata
    - 2.5: Comprehensive error handling
    """
    
    @property
    def EMBEDDING_DIMENSION(self) -> int:
        return _EMBEDDING_DIMENSIONS.get(self.settings.AI_BACKEND, 1536)

    def __init__(
        self,
        collection_name: str = "afterfail_knowledge_v2",
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        use_memory: bool = False,
        settings: Optional[AISettings] = None,
    ):
        """
        Initialize RAG service with Qdrant
        
        Args:
            collection_name: Name of the collection
            qdrant_url: Qdrant server URL (defaults to localhost:6333)
            qdrant_api_key: API key for Qdrant Cloud (optional)
            use_memory: Use in-memory mode instead of server connection
        
        Raises:
            QdrantConnectionError: If Qdrant initialization fails
        """
        self.collection_name = collection_name
        self.settings = settings or config
        
        try:
            # Task 2.2: Initialize Qdrant client
            if use_memory or self.settings.AI_BACKEND == "mock":
                # In-memory mode for testing
                self.client = QdrantClient(":memory:")
            elif qdrant_url or self.settings.QDRANT_URL:
                # Connect to Qdrant server (local or cloud)
                self.client = QdrantClient(
                    url=qdrant_url or self.settings.QDRANT_URL,
                    api_key=qdrant_api_key or self.settings.QDRANT_API_KEY or None
                )
            else:
                # Default: connect to local Qdrant server
                self.client = QdrantClient(
                    host="localhost",
                    port=6333
                )
            
            # 임베딩 초기화: gemini 또는 openai 백엔드 선택
            if self.settings.AI_BACKEND == "mock":
                self.embeddings = _OfflineEmbeddings(self.EMBEDDING_DIMENSION)
            elif self.settings.AI_BACKEND == "gemini":
                gemini_key = self.settings.GEMINI_API_KEY
                if not gemini_key:
                    raise RAGServiceError("Gemini API key not configured")
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model=self.settings.GEMINI_EMBEDDING_MODEL,
                    google_api_key=gemini_key,
                )
            else:
                api_key = self.settings.OPENAI_API_KEY
                if not api_key or api_key == "your_openai_api_key_here":
                    raise RAGServiceError("OpenAI API key not configured")
                self.embeddings = OpenAIEmbeddings(
                    openai_api_key=api_key,
                    model=self.settings.EMBEDDING_MODEL,
                )
            
            # Task 2.3: Create collection if it doesn't exist
            self._ensure_collection_exists()
            
        except Exception as exc:
            raise QdrantConnectionError(
                "Failed to initialize Qdrant/RAG service"
            ) from exc
    
    def _ensure_collection_exists(self):
        """
        Ensure collection exists with proper configuration.
        차원이 다르면 기존 컬렉션을 보존하고 새 versioned collection을 만든다.
        """
        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            target_dim = self.EMBEDDING_DIMENSION

            if self.collection_name in collection_names:
                # 기존 컬렉션 차원 확인
                info = self.client.get_collection(self.collection_name)
                existing_dim = info.config.params.vectors.size
                if existing_dim != target_dim:
                    suffix = hashlib.sha256(
                        f"{self.collection_name}:{target_dim}".encode("utf-8")
                    ).hexdigest()[:8]
                    self.collection_name = f"{self.collection_name}_dim{target_dim}_{suffix}"
                    if self.collection_name in collection_names:
                        return
                else:
                    print(f"Collection already exists: {self.collection_name} (dim={existing_dim})")
                    return

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=target_dim,
                    distance=Distance.COSINE,
                ),
            )
            print(f"Created collection: {self.collection_name} (dim={target_dim})")

        except Exception as e:
            raise QdrantConnectionError(f"Failed to ensure collection exists: {str(e)}")
    
    def load_documents(self, directory: str = "./knowledge-base") -> List[Document]:
        """
        Load markdown documents from directory
        
        Args:
            directory: Directory containing markdown files
        
        Returns:
            List of Document objects
        
        Raises:
            RAGServiceError: If document loading fails
        """
        try:
            if not os.path.exists(directory):
                raise RAGServiceError(f"Directory not found: {directory}")
            
            documents = []
            
            for filename in os.listdir(directory):
                if filename.endswith('.md'):
                    filepath = os.path.join(directory, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                        documents.append(Document(
                            page_content=content,
                            metadata={
                                "source": filename,
                                "type": "markdown",
                                "filepath": filepath
                            }
                        ))
                    except Exception as e:
                        print(f"Warning: Failed to load {filename}: {str(e)}")
                        continue
            
            if not documents:
                raise RAGServiceError(f"No markdown documents found in {directory}")
            
            return documents
            
        except RAGServiceError:
            raise
        except Exception as e:
            raise RAGServiceError(f"Failed to load documents: {str(e)}")
    
    def chunk_documents(
        self,
        documents: List[Document],
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
    ) -> List[Document]:
        """
        Split documents into chunks
        Uses RecursiveCharacterTextSplitter to preserve code blocks
        
        Args:
            documents: List of documents to chunk
            chunk_size: Size of each chunk (defaults to config)
            chunk_overlap: Overlap between chunks (defaults to config)
        
        Returns:
            List of chunked documents
        
        Raises:
            RAGServiceError: If chunking fails
        """
        try:
            if not documents:
                return []
            
            chunk_size = self.settings.RAG_CHUNK_SIZE if chunk_size is None else chunk_size
            chunk_overlap = (
                self.settings.RAG_CHUNK_OVERLAP
                if chunk_overlap is None
                else chunk_overlap
            )
            
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", "```", " ", ""],
                keep_separator=True
            )
            
            chunks = text_splitter.split_documents(documents)
            return chunks
            
        except Exception as e:
            raise RAGServiceError(f"Failed to chunk documents: {str(e)}")

    
    @staticmethod
    def _point_id(document: Document, fallback_index: int) -> str:
        metadata = document.metadata
        source_id = str(metadata.get("source_id") or metadata.get("source") or "unknown")
        chunk_index = metadata.get("chunk_index", fallback_index)
        content_hash = str(
            metadata.get("content_hash")
            or hashlib.sha256(document.page_content.encode("utf-8")).hexdigest()
        )
        identity = f"{source_id}:{chunk_index}:{content_hash}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))

    def _existing_points(self) -> dict[str, dict]:
        points: dict[str, dict] = {}
        offset = None
        while True:
            batch, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in batch:
                points[str(point.id)] = dict(point.payload or {})
            if offset is None:
                return points

    def needs_sync(self, documents: List[Document]) -> bool:
        """manifest/content hash 기반 desired point와 현재 collection 차이를 확인한다."""
        desired = {
            self._point_id(document, index): document
            for index, document in enumerate(documents)
        }
        desired_sources = {
            str(doc.metadata.get("source_id") or doc.metadata.get("source") or "unknown")
            for doc in documents
        }
        existing = self._existing_points()
        managed_ids = {
            point_id
            for point_id, payload in existing.items()
            if str(payload.get("source_id") or payload.get("source") or "unknown")
            in desired_sources
        }
        return set(desired) != managed_ids

    def sync_documents(self, documents: List[Document]) -> IngestionReport:
        """현재 source의 chunk를 안정 ID로 동기화하고 stale point를 제거한다."""
        if not documents:
            return IngestionReport()

        desired = {
            self._point_id(document, index): document
            for index, document in enumerate(documents)
        }
        existing = self._existing_points()
        desired_sources = {
            str(doc.metadata.get("source_id") or doc.metadata.get("source") or "unknown")
            for doc in documents
        }
        managed_existing = {
            point_id: payload
            for point_id, payload in existing.items()
            if str(payload.get("source_id") or payload.get("source") or "unknown")
            in desired_sources
        }
        unchanged_ids = set(desired) & set(managed_existing)
        stale_ids = set(managed_existing) - set(desired)
        new_ids = set(desired) - set(managed_existing)
        existing_sources = {
            str(payload.get("source_id") or payload.get("source") or "unknown")
            for payload in managed_existing.values()
        }
        updated_ids = {
            point_id
            for point_id in new_ids
            if str(
                desired[point_id].metadata.get("source_id")
                or desired[point_id].metadata.get("source")
                or "unknown"
            ) in existing_sources
        }

        if new_ids:
            ordered_new_ids = sorted(new_ids)
            self._upsert_documents(
                [desired[point_id] for point_id in ordered_new_ids],
                point_ids=ordered_new_ids,
            )
        if stale_ids:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=sorted(stale_ids)),
                wait=True,
            )

        return IngestionReport(
            added=len(new_ids - updated_ids),
            updated=len(updated_ids),
            deleted=len(stale_ids),
            unchanged=len(unchanged_ids),
        )

    def ingest_documents(self, documents: List[Document]) -> int:
        """
        Generate embeddings and store in Qdrant
        
        Args:
            documents: List of documents to ingest
        
        Returns:
            Number of documents ingested
        
        Raises:
            DocumentIngestionError: If ingestion fails
        """
        return self.sync_documents(documents).total

    def _upsert_documents(
        self,
        documents: List[Document],
        point_ids: Optional[List[str]] = None,
    ) -> None:
        """새롭거나 변경된 chunk만 embedding하고 upsert한다."""
        if not documents:
            return
        
        try:
            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]

            # Gemini free tier: 분당 100건 제한 → 배치 단위로 임베딩
            BATCH_SIZE = 80
            all_embeddings: list = []
            for batch_start in range(0, len(texts), BATCH_SIZE):
                batch_texts = texts[batch_start:batch_start + BATCH_SIZE]
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        batch_embeddings = self.embeddings.embed_documents(batch_texts)
                        all_embeddings.extend(batch_embeddings)
                        print(f"  Embedded {min(batch_start + BATCH_SIZE, len(texts))}/{len(texts)} chunks")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait = 35 * (attempt + 1)
                            print(f"  Rate limit hit, {wait}s 대기 후 재시도...")
                            time.sleep(wait)
                        else:
                            raise DocumentIngestionError(f"Failed to generate embeddings: {str(e)}")
                if batch_start + BATCH_SIZE < len(texts):
                    time.sleep(35)  # 다음 배치 전 rate limit 회복 대기

            # Prepare points for Qdrant
            points = []
            for i, (text, embedding, metadata) in enumerate(zip(texts, all_embeddings, metadatas)):
                point_id = point_ids[i] if point_ids else self._point_id(documents[i], i)

                payload = {
                    "content": text,
                    "source": metadata.get("source", "unknown"),
                    "type": metadata.get("type", "document"),
                    "filepath": metadata.get("filepath", ""),
                    "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                for key, value in metadata.items():
                    if key not in payload:
                        payload[key] = value

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                )

            # Upsert points to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )

        except DocumentIngestionError:
            raise
        except Exception as e:
            raise DocumentIngestionError(f"Failed to ingest documents: {str(e)}")

    def promote_alias(self, alias_name: str) -> None:
        """검증 완료 후에만 alias를 현재 collection으로 원자적으로 전환한다."""
        if self.get_collection_stats()["document_count"] <= 0:
            raise DocumentIngestionError("빈 collection은 운영 alias로 전환할 수 없습니다")

        aliases = {alias.alias_name for alias in self.client.get_aliases().aliases}
        operations = []
        if alias_name in aliases:
            operations.append(
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias_name))
            )
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(
                    collection_name=self.collection_name,
                    alias_name=alias_name,
                )
            )
        )
        self.client.update_collection_aliases(change_aliases_operations=operations)
    
    def search_knowledge(
        self,
        query: str,
        environment: Optional[str] = None,
        fault_type: Optional[str] = None,
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None,
        filter_source: Optional[str] = None,
    ) -> List[RetrievedDocument]:
        """
        Search vector DB for relevant documents using Qdrant

        Args:
            query: User query
            environment: kubernetes, docker, linux 중 검색 대상 환경
            fault_type: Optional chaos/fault type — filters to matching + general docs
            top_k: Number of results to return (defaults to config)
            min_similarity: Minimum similarity threshold 0-1 (defaults to config)
            filter_source: Optional filter by source metadata

        Returns:
            List of retrieved documents with similarity scores

        Raises:
            SearchError: If search fails
        """
        try:
            if environment not in SUPPORTED_ENVIRONMENTS:
                raise SearchError(
                    "environment는 kubernetes, docker, linux 중 하나여야 합니다"
                )
            top_k = self.settings.RAG_TOP_K if top_k is None else top_k
            min_similarity = (
                self.settings.RAG_MIN_SIMILARITY
                if min_similarity is None
                else min_similarity
            )
            if top_k == 0:
                return []
            if top_k < 0:
                raise SearchError("top_k는 0 이상이어야 합니다")

            # Generate query embedding
            query_embedding = self.embeddings.embed_query(query)

            # Prepare filter
            conditions = [
                FieldCondition(
                    key="environments",
                    match=MatchAny(any=[environment, "general"]),
                )
            ]
            if fault_type:
                conditions.append(
                    FieldCondition(
                        key="fault_types",
                        match=MatchAny(any=[fault_type, "general"]),
                    )
                )
            if filter_source:
                conditions.append(
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=filter_source),
                    )
                )
            query_filter = Filter(must=conditions)
            
            # Search similar documents in Qdrant (qdrant-client 1.7+ API)
            try:
                # 신버전 API
                from qdrant_client.models import QueryRequest
                search_results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    limit=top_k,
                    query_filter=query_filter,
                    score_threshold=min_similarity,
                ).points
            except AttributeError:
                # 구버전 fallback
                search_results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    limit=top_k,
                    query_filter=query_filter,
                    score_threshold=min_similarity,
                )

            # Format results
            documents = []
            for result in search_results:
                documents.append(RetrievedDocument(
                    content=result.payload.get("content", ""),
                    similarity=result.score,
                    source=result.payload.get("source", "unknown"),
                    metadata=result.payload
                ))
            
            return documents
            
        except SearchError:
            raise
        except Exception as e:
            raise SearchError(f"Failed to search knowledge base: {str(e)}")
    
    def augment_prompt(
        self,
        base_prompt: str,
        user_question: str,
        environment: Optional[str] = None,
        top_k: int = 3
    ) -> str:
        """
        Augment prompt with relevant knowledge from vector DB
        
        Args:
            base_prompt: Base system prompt
            user_question: User's question
            top_k: Number of documents to retrieve
        
        Returns:
            Augmented prompt with retrieved knowledge
        """
        # Search for relevant docs
        docs = self.search_knowledge(
            user_question, environment=environment, top_k=top_k
        )
        
        if not docs:
            return base_prompt
        
        # Format retrieved knowledge
        knowledge_section = "\n\n=== RELEVANT DOCUMENTATION ===\n"
        for i, doc in enumerate(docs, 1):
            knowledge_section += f"\n[Source {i}: {doc.source}] (Relevance: {doc.similarity:.2f})\n"
            knowledge_section += f"{doc.content}\n"
            knowledge_section += "-" * 80 + "\n"
        
        # Insert knowledge before user question
        augmented_prompt = f"{base_prompt}\n{knowledge_section}\n\nUser Question: {user_question}"
        
        return augmented_prompt
    
    def clear_collection(self):
        """Clear all documents from collection"""
        try:
            self.client.delete_collection(self.collection_name)
            self._ensure_collection_exists()
            print(f"Collection {self.collection_name} cleared and recreated")
        except Exception as e:
            raise RAGServiceError(f"Failed to clear collection: {str(e)}")
    
    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "document_count": collection_info.points_count,
                "vector_dimension": self.EMBEDDING_DIMENSION,
                "distance_metric": "cosine"
            }
        except Exception as e:
            raise RAGServiceError(f"Failed to get collection stats: {str(e)}")


def main():
    """Example usage of RAG service with Qdrant"""
    # Initialize service (use in-memory mode for demo)
    rag = RAGService(use_memory=True)
    
    # Load documents
    print("Loading documents...")
    docs = rag.load_documents()
    print(f"Loaded {len(docs)} documents")
    
    # Chunk documents
    print("Chunking documents...")
    chunks = rag.chunk_documents(docs)
    print(f"Created {len(chunks)} chunks")
    
    # Ingest into vector DB
    print("Ingesting into Qdrant...")
    count = rag.ingest_documents(chunks)
    print(f"Ingested {count} chunks")
    
    # Test search
    print("\nTesting search...")
    query = "Pod is in ImagePullBackOff status"
    results = rag.search_knowledge(query, environment="kubernetes", top_k=2)
    
    print(f"\nQuery: {query}")
    print(f"Found {len(results)} relevant documents:\n")
    
    for doc in results:
        print(f"Source: {doc.source}")
        print(f"Similarity: {doc.similarity:.3f}")
        print(f"Content preview: {doc.content[:200]}...")
        print("-" * 80)
    
    # Show stats
    stats = rag.get_collection_stats()
    print(f"\nCollection Stats: {stats}")


if __name__ == "__main__":
    main()
