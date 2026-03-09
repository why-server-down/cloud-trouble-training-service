"""
RAG Service for AI Tutor System
Handles document loading, chunking, embedding, and retrieval
"""

import os
from typing import List, Dict, Optional
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from dotenv import load_dotenv

load_dotenv()


@dataclass
class RetrievedDocument:
    """Retrieved document with metadata"""
    content: str
    similarity: float
    source: str
    metadata: Dict


class RAGService:
    """
    Retrieval-Augmented Generation service
    Handles vector storage and semantic search
    """
    
    def __init__(
        self,
        collection_name: str = "k8s_docs",
        persist_directory: str = "./vector-db/chroma_data"
    ):
        """Initialize RAG service with ChromaDB"""
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        
        # Initialize ChromaDB client
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
        # Initialize OpenAI embeddings
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Kubernetes documentation and troubleshooting guides"}
        )
    
    def load_documents(self, directory: str = "./knowledge-base") -> List[Document]:
        """
        Load markdown documents from directory
        """
        documents = []
        
        for filename in os.listdir(directory):
            if filename.endswith('.md'):
                filepath = os.path.join(directory, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                documents.append(Document(
                    page_content=content,
                    metadata={
                        "source": filename,
                        "type": "markdown"
                    }
                ))
        
        return documents
    
    def chunk_documents(
        self,
        documents: List[Document],
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Document]:
        """
        Split documents into chunks
        Uses RecursiveCharacterTextSplitter to preserve code blocks
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "```", " ", ""],
            keep_separator=True
        )
        
        chunks = text_splitter.split_documents(documents)
        return chunks

    
    def ingest_documents(self, documents: List[Document]) -> int:
        """
        Generate embeddings and store in ChromaDB
        Returns number of documents ingested
        """
        if not documents:
            return 0
        
        # Prepare data for ChromaDB
        ids = [f"doc_{i}" for i in range(len(documents))]
        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        
        # Generate embeddings
        embeddings_list = self.embeddings.embed_documents(texts)
        
        # Add to collection
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings_list,
            metadatas=metadatas
        )
        
        return len(documents)
    
    def search_knowledge(
        self,
        query: str,
        top_k: int = 3,
        min_similarity: float = 0.7
    ) -> List[RetrievedDocument]:
        """
        Search vector DB for relevant documents
        
        Args:
            query: User query
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold (0-1)
        
        Returns:
            List of retrieved documents with similarity scores
        """
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
