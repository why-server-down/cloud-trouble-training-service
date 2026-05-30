"""
Qdrant RAG Service - Quick Start Example
Demonstrates basic usage of the Qdrant-based RAG system
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rag_service import RAGService
from langchain.schema import Document


def example_1_inmemory():
    """Example 1: Using in-memory Qdrant (no server required)"""
    print("=" * 80)
    print("Example 1: In-Memory Qdrant")
    print("=" * 80)
    
    # Initialize with in-memory mode
    rag = RAGService(
        collection_name="demo_k8s",
        use_memory=True
    )
    
    # Create sample documents
    docs = [
        Document(
            page_content="Pod is in CrashLoopBackOff status. Check container logs with kubectl logs <pod-name>.",
            metadata={"source": "troubleshooting.md", "category": "errors"}
        ),
        Document(
            page_content="ImagePullBackOff error occurs when Kubernetes cannot pull the container image. Verify image name and registry credentials.",
            metadata={"source": "troubleshooting.md", "category": "errors"}
        ),
        Document(
            page_content="Use kubectl describe pod <pod-name> to see detailed information including events and status.",
            metadata={"source": "commands.md", "category": "reference"}
        ),
        Document(
            page_content="kubectl get pods -o wide shows pods with additional information like node and IP address.",
            metadata={"source": "commands.md", "category": "reference"}
        )
    ]
    
    # Ingest documents
    print(f"\nIngesting {len(docs)} documents...")
    count = rag.ingest_documents(docs)
    print(f"✓ Ingested {count} documents")
    
    # Get stats
    stats = rag.get_collection_stats()
    print(f"\nCollection Stats:")
    print(f"  - Name: {stats['collection_name']}")
    print(f"  - Documents: {stats['document_count']}")
    print(f"  - Dimension: {stats['vector_dimension']}")
    print(f"  - Distance: {stats['distance_metric']}")
    
    # Search
    print("\n" + "-" * 80)
    query = "Why is my pod crashing?"
    print(f"Query: {query}")
    print("-" * 80)
    
    results = rag.search_knowledge(query, top_k=2)
    
    for i, doc in enumerate(results, 1):
        print(f"\nResult {i}:")
        print(f"  Source: {doc.source}")
        print(f"  Similarity: {doc.similarity:.3f}")
        print(f"  Content: {doc.content[:150]}...")
    
    print("\n")


def example_2_local_server():
    """Example 2: Using local Qdrant server"""
    print("=" * 80)
    print("Example 2: Local Qdrant Server")
    print("=" * 80)
    print("\nNote: This requires Qdrant server running on localhost:6333")
    print("Start server with: docker run -p 6333:6333 qdrant/qdrant")
    print()
    
    try:
        # Initialize with local server
        rag = RAGService(
            collection_name="k8s_docs",
            qdrant_url="http://localhost:6333"
        )
        
        # Create sample document
        docs = [
            Document(
                page_content="Kubernetes Pod lifecycle: Pending → Running → Succeeded/Failed",
                metadata={"source": "concepts.md", "topic": "lifecycle"}
            )
        ]
        
        # Ingest
        print("Ingesting documents...")
        count = rag.ingest_documents(docs)
        print(f"✓ Ingested {count} documents")
        
        # Search
        results = rag.search_knowledge("Pod lifecycle", top_k=1)
        print(f"\nFound {len(results)} results")
        
        if results:
            print(f"Content: {results[0].content}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        print("Make sure Qdrant server is running!")
    
    print("\n")


def example_3_metadata_filtering():
    """Example 3: Search with metadata filtering"""
    print("=" * 80)
    print("Example 3: Metadata Filtering")
    print("=" * 80)
    
    # Initialize
    rag = RAGService(
        collection_name="demo_filtered",
        use_memory=True
    )
    
    # Create documents with different sources
    docs = [
        Document(
            page_content="kubectl get pods lists all pods in the current namespace.",
            metadata={"source": "commands.md", "type": "command"}
        ),
        Document(
            page_content="Pods are the smallest deployable units in Kubernetes.",
            metadata={"source": "concepts.md", "type": "concept"}
        ),
        Document(
            page_content="kubectl describe pod shows detailed pod information.",
            metadata={"source": "commands.md", "type": "command"}
        )
    ]
    
    # Ingest
    print(f"\nIngesting {len(docs)} documents...")
    rag.ingest_documents(docs)
    
    # Search without filter
    print("\n" + "-" * 80)
    print("Search: 'kubectl' (no filter)")
    print("-" * 80)
    results = rag.search_knowledge("kubectl", top_k=3)
    print(f"Found {len(results)} results:")
    for r in results:
        print(f"  - {r.source}: {r.content[:50]}...")
    
    # Search with filter
    print("\n" + "-" * 80)
    print("Search: 'kubectl' (filter: source=commands.md)")
    print("-" * 80)
    results = rag.search_knowledge("kubectl", top_k=3, filter_source="commands.md")
    print(f"Found {len(results)} results:")
    for r in results:
        print(f"  - {r.source}: {r.content[:50]}...")
    
    print("\n")


def example_4_prompt_augmentation():
    """Example 4: RAG-augmented prompt generation"""
    print("=" * 80)
    print("Example 4: Prompt Augmentation")
    print("=" * 80)
    
    # Initialize
    rag = RAGService(
        collection_name="demo_rag",
        use_memory=True
    )
    
    # Add knowledge base
    docs = [
        Document(
            page_content="To debug a CrashLoopBackOff, first check logs with 'kubectl logs <pod>', then check events with 'kubectl describe pod <pod>'.",
            metadata={"source": "debugging.md"}
        ),
        Document(
            page_content="Common causes of CrashLoopBackOff: application errors, missing dependencies, incorrect configuration, resource limits.",
            metadata={"source": "troubleshooting.md"}
        )
    ]
    
    print(f"\nBuilding knowledge base with {len(docs)} documents...")
    rag.ingest_documents(docs)
    
    # Create augmented prompt
    base_prompt = "You are a Kubernetes expert assistant. Help users troubleshoot their issues."
    user_question = "My pod keeps crashing, what should I do?"
    
    augmented_prompt = rag.augment_prompt(base_prompt, user_question, top_k=2)
    
    print("\n" + "-" * 80)
    print("Augmented Prompt:")
    print("-" * 80)
    print(augmented_prompt)
    print("\n")


def main():
    """Run all examples"""
    print("\n")
    print("🚀 Qdrant RAG Service - Quick Start Examples")
    print("=" * 80)
    print()
    
    # Run examples
    example_1_inmemory()
    example_3_metadata_filtering()
    example_4_prompt_augmentation()
    
    # Optional: local server example
    print("=" * 80)
    print("Optional: Run example_2_local_server() if you have Qdrant server running")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
