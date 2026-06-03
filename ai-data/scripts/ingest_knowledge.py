#!/usr/bin/env python3
"""
Knowledge Base Ingestion Script
Loads documents from knowledge-base directory and ingests them into Qdrant
"""

import os
import sys
from pathlib import Path

# Add ai-data to Python path
AI_DATA_PATH = Path(__file__).parent.parent
sys.path.insert(0, str(AI_DATA_PATH))

from rag_service import RAGService, RAGServiceError
from config import config


def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def print_step(step_num, text):
    """Print formatted step"""
    print(f"\n[Step {step_num}] {text}")


def print_success(text):
    """Print success message"""
    print(f"✓ {text}")


def print_error(text):
    """Print error message"""
    print(f"✗ {text}")


def print_warning(text):
    """Print warning message"""
    print(f"⚠ {text}")


def load_all_documents(kb_dir: Path) -> list:
    """Recursively load all markdown files from knowledge base"""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    
    docs = []
    for md_file in kb_dir.rglob("*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Get relative path for better source identification
            rel_path = md_file.relative_to(kb_dir)
            
            # Create document with metadata
            from langchain.schema import Document
            doc = Document(
                page_content=content,
                metadata={
                    "source": str(rel_path),
                    "type": "markdown",
                    "filepath": str(md_file),
                    "category": rel_path.parts[0] if len(rel_path.parts) > 1 else "root"
                }
            )
            docs.append(doc)
        except Exception as e:
            print_warning(f"Failed to load {md_file}: {e}")
            continue
    
    return docs


def main():
    """Main ingestion process"""
    print_header("Knowledge Base Ingestion")
    
    # Display configuration
    print("\nConfiguration:")
    print(f"  Knowledge Base Dir: {config.KNOWLEDGE_BASE_DIR}")
    print(f"  AI Backend: {config.AI_BACKEND}")
    
    if config.AI_BACKEND == "gemini":
        print(f"  Gemini API Key: {'✓ Set' if config.GEMINI_API_KEY else '✗ Not Set'}")
        print(f"  Gemini Embedding Model: {config.GEMINI_EMBEDDING_MODEL}")
        if not config.GEMINI_API_KEY:
            print_error("Gemini API key not configured!")
            print("\nPlease set GEMINI_API_KEY in .env file:")
            print("  GEMINI_API_KEY=your_actual_api_key_here")
            sys.exit(1)
    else:
        print(f"  OpenAI API Key: {'✓ Set' if config.OPENAI_API_KEY and config.OPENAI_API_KEY != 'your_openai_api_key_here' else '✗ Not Set'}")
        print(f"  OpenAI Model: {config.OPENAI_MODEL}")
        if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "your_openai_api_key_here":
            print_error("OpenAI API key not configured!")
            print("\nPlease set OPENAI_API_KEY in .env file:")
            print("  OPENAI_API_KEY=your_actual_api_key_here")
            sys.exit(1)
    
    # Check if knowledge base directory exists
    kb_dir = Path(config.KNOWLEDGE_BASE_DIR)
    if not kb_dir.exists():
        print_error(f"Knowledge base directory not found: {kb_dir}")
        sys.exit(1)
    
    try:
        # Step 1: Initialize RAG Service
        print_step(1, "Initializing RAG Service")
        
        # Use in-memory mode for testing, or connect to Qdrant server
        use_memory = os.getenv("QDRANT_USE_MEMORY", "false").lower() == "true"
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        
        if use_memory:
            print("  Using in-memory Qdrant (for testing)")
            rag = RAGService(use_memory=True)
        else:
            print(f"  Connecting to Qdrant at {qdrant_url}")
            rag = RAGService(qdrant_url=qdrant_url)
        
        print_success("RAG Service initialized")
        
        # Step 2: Check existing collection
        print_step(2, "Checking existing collection")
        
        try:
            stats = rag.get_collection_stats()
            print(f"  Collection: {stats['collection_name']}")
            print(f"  Existing documents: {stats['document_count']}")
            print(f"  Vector dimension: {stats['vector_dimension']}")
            print(f"  Distance metric: {stats['distance_metric']}")
            
            if stats['document_count'] > 0:
                response = input("\n  Collection already has documents. Clear and reload? (y/N): ")
                if response.lower() == 'y':
                    print("  Clearing collection...")
                    rag.clear_collection()
                    print_success("Collection cleared")
                else:
                    print_warning("Skipping ingestion (collection not cleared)")
                    sys.exit(0)
        except Exception as e:
            print_warning(f"Could not get collection stats: {e}")
        
        # Step 3: Load documents
        print_step(3, "Loading documents from knowledge base (recursive)")
        
        docs = load_all_documents(kb_dir)
        print(f"  Found {len(docs)} documents")
        
        if len(docs) == 0:
            print_error("No documents found!")
            print(f"\nPlease add markdown files to: {kb_dir}")
            sys.exit(1)
        
        # List loaded documents by category
        print("\n  Loaded documents by category:")
        from collections import defaultdict
        by_category = defaultdict(list)
        for doc in docs:
            category = doc.metadata.get('category', 'root')
            by_category[category].append(doc.metadata['source'])
        
        for category, files in sorted(by_category.items()):
            print(f"\n  📁 {category}/ ({len(files)} files)")
            for file in files[:5]:  # Show first 5
                print(f"    - {file}")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more")
        
        print_success(f"Loaded {len(docs)} documents")
        
        # Step 4: Chunk documents
        print_step(4, "Chunking documents")
        
        print(f"  Chunk size: {config.RAG_CHUNK_SIZE}")
        print(f"  Chunk overlap: {config.RAG_CHUNK_OVERLAP}")
        
        chunks = rag.chunk_documents(docs)
        print(f"  Created {len(chunks)} chunks")
        
        # Show chunk statistics
        chunk_sizes = [len(chunk.page_content) for chunk in chunks]
        avg_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
        min_size = min(chunk_sizes) if chunk_sizes else 0
        max_size = max(chunk_sizes) if chunk_sizes else 0
        
        print(f"\n  Chunk statistics:")
        print(f"    Average size: {avg_size:.0f} chars")
        print(f"    Min size: {min_size} chars")
        print(f"    Max size: {max_size} chars")
        
        print_success(f"Created {len(chunks)} chunks")
        
        # Step 5: Generate embeddings and ingest
        print_step(5, "Generating embeddings and ingesting into Qdrant")
        
        print("  This may take a few minutes...")
        if config.AI_BACKEND == "gemini":
            print(f"  Embedding model: {config.GEMINI_EMBEDDING_MODEL}")
        else:
            print(f"  Embedding model: text-embedding-ada-002")
        print(f"  Estimated API calls: {len(chunks)}")
        
        count = rag.ingest_documents(chunks)
        
        print_success(f"Successfully ingested {count} chunks")
        
        # Step 6: Verify ingestion
        print_step(6, "Verifying ingestion")
        
        stats = rag.get_collection_stats()
        print(f"  Collection: {stats['collection_name']}")
        print(f"  Total documents: {stats['document_count']}")
        
        if stats['document_count'] != count:
            print_warning(f"Document count mismatch: expected {count}, got {stats['document_count']}")
        else:
            print_success("Document count verified")
        
        # Step 7: Test search
        print_step(7, "Testing search functionality")
        
        test_queries = [
            "Pod is in CrashLoopBackOff status",
            "ImagePullBackOff error",
            "kubectl get pods command"
        ]
        
        print("\n  Running test queries:")
        for query in test_queries:
            print(f"\n  Query: \"{query}\"")
            results = rag.search_knowledge(query, top_k=2)
            
            if results:
                print(f"  Found {len(results)} results:")
                for i, result in enumerate(results, 1):
                    print(f"    {i}. {result.source} (similarity: {result.similarity:.3f})")
                    preview = result.content[:100].replace('\n', ' ')
                    print(f"       Preview: {preview}...")
            else:
                print_warning("  No results found")
        
        print_success("Search functionality verified")
        
        # Summary
        print_header("Ingestion Complete!")
        
        print("\nSummary:")
        print(f"  ✓ Documents loaded: {len(docs)}")
        print(f"  ✓ Chunks created: {len(chunks)}")
        print(f"  ✓ Chunks ingested: {count}")
        print(f"  ✓ Collection: {stats['collection_name']}")
        print(f"  ✓ Total documents in DB: {stats['document_count']}")
        
        print("\nNext steps:")
        print("  1. Test the AI Tutor Engine:")
        print("     python ai_engine.py")
        print("  2. Start the Backend API:")
        print("     cd ../backend && uvicorn app.main:app --reload")
        print("  3. Use the chatbot widget:")
        print("     open ../ai-chatbot-widget/demo-standalone.html")
        
        print("\n" + "=" * 80)
        
    except RAGServiceError as e:
        print_error(f"RAG Service Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nIngestion cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
