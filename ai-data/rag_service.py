"""
RAG Service for AI Tutor System
Handles document loading, chunking, embedding, and retrieval

Task 2: Vector Database Setup (Migrated to Qdrant)
- 2.2: Configure Qdrant client with error handling
- 2.3: Create collection for K8s docs with proper settings
- 2.5: Add comprehensive error handling
"""

import os
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
    MatchValue
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document
from dotenv import load_dotenv

from config import config

load_dotenv()

# 임베딩 차원: OpenAI text-embedding-ada-002=1536, Gemini gemini-embedding-001=3072
_EMBEDDING_DIMENSIONS = {
    "openai": 1536,
    "gemini": 3072,
}


@dataclass
class RetrievedDocument:
    """Retrieved document with metadata"""
    content: str
    similarity: float
    source: str
    metadata: Dict


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
        return _EMBEDDING_DIMENSIONS.get(config.AI_BACKEND, 1536)

    def __init__(
        self,
        collection_name: str = "k8s_docs",
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        use_memory: bool = False
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
        
        try:
            # Task 2.2: Initialize Qdrant client
            if use_memory:
                # In-memory mode for testing
                self.client = QdrantClient(":memory:")
            elif qdrant_url or config.QDRANT_URL:
                # Connect to Qdrant server (local or cloud)
                self.client = QdrantClient(
                    url=qdrant_url or config.QDRANT_URL,
                    api_key=qdrant_api_key or config.QDRANT_API_KEY or None
                )
            else:
                # Default: connect to local Qdrant server
                self.client = QdrantClient(
                    host="localhost",
                    port=6333
                )
            
            # 임베딩 초기화: gemini 또는 openai 백엔드 선택
            if config.AI_BACKEND == "gemini":
                gemini_key = config.GEMINI_API_KEY
                if not gemini_key:
                    raise RAGServiceError("Gemini API key not configured")
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model=config.GEMINI_EMBEDDING_MODEL,
                    google_api_key=gemini_key,
                )
            else:
                api_key = config.OPENAI_API_KEY
                if not api_key or api_key == "your_openai_api_key_here":
                    raise RAGServiceError("OpenAI API key not configured")
                self.embeddings = OpenAIEmbeddings(
                    openai_api_key=api_key,
                    model="text-embedding-ada-002",
                )
            
            # Task 2.3: Create collection if it doesn't exist
            self._ensure_collection_exists()
            
        except Exception as e:
            raise QdrantConnectionError(f"Failed to initialize Qdrant: {str(e)}")
    
    def _ensure_collection_exists(self):
        """
        Ensure collection exists with proper configuration.
        차원이 현재 임베딩 모델과 다르면 컬렉션을 삭제하고 재생성한다.
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
                    print(f"Dimension mismatch ({existing_dim} → {target_dim}), recreating collection.")
                    self.client.delete_collection(self.collection_name)
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
            
            chunk_size = chunk_size or config.RAG_CHUNK_SIZE
            chunk_overlap = chunk_overlap or config.RAG_CHUNK_OVERLAP
            
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
        if not documents:
            return 0
        
        try:
            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]
            
            # Generate embeddings with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    embeddings_list = self.embeddings.embed_documents(texts)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"Embedding attempt {attempt + 1} failed, retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise DocumentIngestionError(f"Failed to generate embeddings: {str(e)}")
            
            # Prepare points for Qdrant
            points = []
            for i, (text, embedding, metadata) in enumerate(zip(texts, embeddings_list, metadatas)):
                point_id = str(uuid.uuid4())
                
                # Prepare payload (metadata + content)
                payload = {
                    "content": text,
                    "source": metadata.get("source", "unknown"),
                    "type": metadata.get("type", "document"),
                    "filepath": metadata.get("filepath", ""),
                    "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Add any additional metadata fields
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
            
            return len(documents)
            
        except DocumentIngestionError:
            raise
        except Exception as e:
            raise DocumentIngestionError(f"Failed to ingest documents: {str(e)}")
    
    def search_knowledge(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None,
        filter_source: Optional[str] = None
    ) -> List[RetrievedDocument]:
        """
        Search vector DB for relevant documents using Qdrant
        
        Args:
            query: User query
            top_k: Number of results to return (defaults to config)
            min_similarity: Minimum similarity threshold 0-1 (defaults to config)
            filter_source: Optional filter by source metadata
        
        Returns:
            List of retrieved documents with similarity scores
        
        Raises:
            SearchError: If search fails
        """
        try:
            top_k = top_k or config.RAG_TOP_K
            min_similarity = min_similarity or config.RAG_MIN_SIMILARITY
            
            # Generate query embedding
            query_embedding = self.embeddings.embed_query(query)
            
            # Prepare filter if source is specified
            query_filter = None
            if filter_source:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=filter_source)
                        )
                    ]
                )
            
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
            
        except Exception as e:
            raise SearchError(f"Failed to search knowledge base: {str(e)}")
    
    def augment_prompt(
        self,
        base_prompt: str,
        user_question: str,
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
        docs = self.search_knowledge(user_question, top_k=top_k)
        
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
    results = rag.search_knowledge(query, top_k=2)
    
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
