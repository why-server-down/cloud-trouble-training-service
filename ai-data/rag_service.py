"""
RAG Service for AI Tutor System
Handles document loading, chunking, embedding, and retrieval

Task 2: Vector Database Setup
- 2.2: Configure ChromaDB client with error handling
- 2.3: Create collection for K8s docs with proper settings
- 2.5: Add comprehensive error handling
"""

import os
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from dotenv import load_dotenv

from config import config

load_dotenv()


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


class ChromaDBConnectionError(RAGServiceError):
    """ChromaDB connection error"""
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
    Handles vector storage and semantic search
    
    Task 2 Implementation:
    - 2.2: ChromaDB client with config integration
    - 2.3: K8s docs collection with metadata
    - 2.5: Comprehensive error handling
    """
    
    def __init__(
        self,
        collection_name: str = "k8s_docs",
        persist_directory: Optional[str] = None
    ):
        """
        Initialize RAG service with ChromaDB
        
        Args:
            collection_name: Name of the collection
            persist_directory: Directory to persist data (defaults to config)
        
        Raises:
            ChromaDBConnectionError: If ChromaDB initialization fails
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory or config.CHROMADB_PERSIST_DIR
        
        try:
            # Task 2.2: Initialize ChromaDB client with proper settings
            os.makedirs(self.persist_directory, exist_ok=True)
            
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Task 2.2: Initialize OpenAI embeddings with error handling
            api_key = config.OPENAI_API_KEY
            if not api_key or api_key == "your_openai_api_key_here":
                raise RAGServiceError("OpenAI API key not configured")
            
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=api_key,
                model="text-embedding-ada-002"
            )
            
            # Task 2.3: Get or create collection with K8s-specific metadata
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={
                    "description": "Kubernetes documentation and troubleshooting guides",
                    "type": "k8s_knowledge",
                    "embedding_model": "text-embedding-ada-002",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            )
            
        except Exception as e:
            raise ChromaDBConnectionError(f"Failed to initialize ChromaDB: {str(e)}")
    
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
        Generate embeddings and store in ChromaDB
        
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
            # Prepare data for ChromaDB
            ids = [f"doc_{i}_{int(time.time())}" for i in range(len(documents))]
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
            
            # Add to collection
            self.collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings_list,
                metadatas=metadatas
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
        min_similarity: Optional[float] = None
    ) -> List[RetrievedDocument]:
        """
        Search vector DB for relevant documents
        
        Args:
            query: User query
            top_k: Number of results to return (defaults to config)
            min_similarity: Minimum similarity threshold 0-1 (defaults to config)
        
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
            
            # Search similar documents
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            # Filter by similarity threshold and format results
            documents = []
            
            if results['documents'] and results['documents'][0]:
                for i, (doc, distance, metadata) in enumerate(zip(
                    results['documents'][0],
                    results['distances'][0],
                    results['metadatas'][0]
                )):
                    # Convert distance to similarity (ChromaDB uses L2 distance)
                    similarity = 1 / (1 + distance)
                    
                    if similarity >= min_similarity:
                        documents.append(RetrievedDocument(
                            content=doc,
                            similarity=similarity,
                            source=metadata.get('source', 'unknown'),
                            metadata=metadata
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
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Kubernetes documentation and troubleshooting guides"}
        )
    
    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection"""
        count = self.collection.count()
        return {
            "collection_name": self.collection_name,
            "document_count": count,
            "persist_directory": self.persist_directory
        }


def main():
    """Example usage of RAG service"""
    # Initialize service
    rag = RAGService()
    
    # Load documents
    print("Loading documents...")
    docs = rag.load_documents()
    print(f"Loaded {len(docs)} documents")
    
    # Chunk documents
    print("Chunking documents...")
    chunks = rag.chunk_documents(docs)
    print(f"Created {len(chunks)} chunks")
    
    # Ingest into vector DB
    print("Ingesting into ChromaDB...")
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
