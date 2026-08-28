"""
Test script for RAG system
Tests document loading, embedding, and retrieval
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_service import RAGService
from prompt_engine import SocraticPromptEngine, MissionContext, SystemContext, UserContext
from ai_engine import AITutorEngine, TutorRequest


def test_rag_service():
    """Test RAG service independently"""
    print("="*80)
    print("TEST 1: RAG Service")
    print("="*80)
    
    rag = RAGService()
    
    # Load and ingest documents
    print("\n1. Loading documents...")
    docs = rag.load_documents()
    print(f"   ✓ Loaded {len(docs)} documents")
    
    print("\n2. Chunking documents...")
    chunks = rag.chunk_documents(docs)
    print(f"   ✓ Created {len(chunks)} chunks")
    
    print("\n3. Ingesting into ChromaDB...")
    count = rag.ingest_documents(chunks)
    print(f"   ✓ Ingested {count} chunks")
    
    # Test search
    print("\n4. Testing search...")
    test_queries = [
        "ImagePullBackOff error",
        "CrashLoopBackOff troubleshooting",
        "Service not accessible"
    ]
    
    for query in test_queries:
        print(f"\n   Query: '{query}'")
        results = rag.search_knowledge(query, top_k=2)
        print(f"   Found {len(results)} results:")
        for doc in results:
            print(f"     - {doc.source} (similarity: {doc.similarity:.3f})")
    
    # Show stats
    stats = rag.get_collection_stats()
    print(f"\n5. Collection stats:")
    print(f"   {stats}")
    
    print("\n✓ RAG Service test completed\n")


def test_prompt_engine():
    """Test prompt engine independently"""
    print("="*80)
    print("TEST 2: Prompt Engine")
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
    
    # Test each hint level
    question = "My pod is not starting. What should I do?"
    
    for level in range(4):
        print(f"\n{level+1}. Testing Hint Level {level}...")
        prompt = engine.generate_prompt(
            user_question=question,
            hint_level=level,
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        print(f"   ✓ Generated prompt ({len(prompt)} chars)")
        print(f"   Preview: {prompt[:150]}...")
    
    print("\n✓ Prompt Engine test completed\n")


def test_ai_engine():
    """Test complete AI engine"""
    print("="*80)
    print("TEST 3: AI Engine (Full Integration)")
    print("="*80)
    
    print("\n1. Initializing AI Engine...")
    engine = AITutorEngine(use_rag=True)
    print("   ✓ Engine initialized")
    
    print("\n2. Initializing knowledge base...")
    engine.initialize_knowledge_base()
    print("   ✓ Knowledge base ready")
    
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
    
    # Test questions at different hint levels
    test_cases = [
        (0, "My pod is not starting. What should I check?"),
        (1, "I see ImagePullBackOff. What does that mean?"),
        (2, "How do I investigate this image pull error?"),
    ]
    
    print("\n3. Testing AI responses...")
    for hint_level, question in test_cases:
        print(f"\n   Hint Level {hint_level}: '{question}'")
        
        request = TutorRequest(
            user_question=question,
            hint_level=hint_level,
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        
        response = engine.get_response(request)
        
        print(f"   ✓ Response generated")
        print(f"     Length: {len(response.message)} chars")
        print(f"     Sources: {len(response.sources)}")
        print(f"     Tokens: {response.token_usage.get('total_tokens', 0)}")
        print(f"     Preview: {response.message[:200]}...")
        
        user.hint_count += 1
        user.previous_questions.append(question)
    
    print("\n✓ AI Engine test completed\n")


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("AI TUTOR SYSTEM - RAG TEST SUITE")
    print("="*80 + "\n")
    
    try:
        # Test 1: RAG Service
        test_rag_service()
        
        # Test 2: Prompt Engine
        test_prompt_engine()
        
        # Test 3: Full AI Engine (requires OpenAI API key)
        print("⚠️  Test 3 requires OpenAI API key")
        import os
        if os.getenv("OPENAI_API_KEY"):
            test_ai_engine()
        else:
            print("   Skipping (no API key found)\n")
        
        print("="*80)
        print("✓ ALL TESTS COMPLETED SUCCESSFULLY")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}\n")
        raise


if __name__ == "__main__":
    main()
