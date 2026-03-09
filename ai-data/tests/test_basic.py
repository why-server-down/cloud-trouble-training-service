"""
Basic test without OpenAI API
Tests document loading and chunking only
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_service import RAGService
from prompt_engine import SocraticPromptEngine, MissionContext, SystemContext, UserContext


def test_document_loading():
    """Test document loading"""
    print("="*80)
    print("TEST: Document Loading")
    print("="*80)
    
    rag = RAGService()
    
    print("\n1. Loading documents from knowledge-base...")
    docs = rag.load_documents()
    print(f"   ✓ Loaded {len(docs)} documents")
    
    for doc in docs:
        print(f"     - {doc.metadata['source']}: {len(doc.page_content)} chars")
    
    return docs


def test_chunking(docs):
    """Test document chunking"""
    print("\n" + "="*80)
    print("TEST: Document Chunking")
    print("="*80)
    
    rag = RAGService()
    
    print("\n1. Chunking documents...")
    chunks = rag.chunk_documents(docs, chunk_size=500, chunk_overlap=100)
    print(f"   ✓ Created {len(chunks)} chunks")
    
    print("\n2. Sample chunks:")
    for i, chunk in enumerate(chunks[:3], 1):
        print(f"\n   Chunk {i}:")
        print(f"   Source: {chunk.metadata['source']}")
        print(f"   Length: {len(chunk.page_content)} chars")
        print(f"   Preview: {chunk.page_content[:150]}...")
    
    return chunks


def test_prompt_generation():
    """Test prompt generation"""
    print("\n" + "="*80)
    print("TEST: Prompt Generation")
    print("="*80)
    
    engine = SocraticPromptEngine()
    
    # Create test contexts
    mission = MissionContext(
        mission_id="m1",
        mission_name="ImagePullBackOff Challenge",
        mission_level=1,
        chaos_type="image_pull_error",
        expected_solution="Fix image name"
    )
    
    system = SystemContext(
        namespace="user-123",
        pod_status="ImagePullBackOff",
        pod_logs="Error: Failed to pull image 'ngnix:latest'",
        recent_events="Failed to pull image: NotFound"
    )
    
    user = UserContext(
        user_id="user-123",
        hint_count=0,
        previous_questions=[]
    )
    
    question = "My pod is not starting. What should I do?"
    
    print("\n1. Generating prompts for each hint level...")
    for level in range(4):
        prompt = engine.generate_prompt(
            user_question=question,
            hint_level=level,
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        print(f"\n   Hint Level {level}:")
        print(f"   Prompt length: {len(prompt)} chars")
        print(f"   Contains hint instruction: {'HINT LEVEL' in prompt}")


def main():
    """Run basic tests"""
    print("\n" + "="*80)
    print("AI TUTOR SYSTEM - BASIC TEST (No API Key Required)")
    print("="*80 + "\n")
    
    try:
        # Test 1: Document Loading
        docs = test_document_loading()
        
        # Test 2: Chunking
        chunks = test_chunking(docs)
        
        # Test 3: Prompt Generation
        test_prompt_generation()
        
        print("\n" + "="*80)
        print("✓ ALL BASIC TESTS PASSED")
        print("="*80)
        print("\nNext steps:")
        print("1. Add your OpenAI API key to .env file")
        print("2. Run: python test_rag.py (for full RAG test)")
        print("3. Run: python ai_engine.py (for complete AI engine test)")
        print()
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
