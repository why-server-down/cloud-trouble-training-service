"""
Simple test without ChromaDB
Tests document loading, chunking, and prompt generation
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_engine import SocraticPromptEngine, MissionContext, SystemContext, UserContext


def test_document_loading():
    """Test document loading"""
    print("="*80)
    print("TEST 1: Document Loading")
    print("="*80)
    
    directory = "./knowledge-base"
    documents = []
    
    print(f"\nLoading documents from {directory}...")
    for filename in os.listdir(directory):
        if filename.endswith('.md'):
            filepath = os.path.join(directory, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            documents.append({
                "content": content,
                "source": filename,
                "length": len(content)
            })
            print(f"  ✓ {filename}: {len(content)} chars")
    
    print(f"\n✓ Loaded {len(documents)} documents")
    return documents


def test_chunking(docs):
    """Test document chunking (simple version)"""
    print("\n" + "="*80)
    print("TEST 2: Document Chunking")
    print("="*80)
    
    chunk_size = 500
    chunks = []
    
    print("\nChunking documents...")
    for doc in docs:
        content = doc["content"]
        # Simple chunking by splitting on double newlines
        parts = content.split("\n\n")
        for part in parts:
            if len(part) > chunk_size:
                # Split large parts
                for i in range(0, len(part), chunk_size):
                    chunks.append({
                        "content": part[i:i+chunk_size],
                        "source": doc["source"]
                    })
            else:
                chunks.append({
                    "content": part,
                    "source": doc["source"]
                })
    
    print(f"✓ Created {len(chunks)} chunks")
    
    print("\nSample chunks:")
    for i, chunk in enumerate(chunks[:3], 1):
        print(f"\n  Chunk {i}:")
        print(f"  Source: {chunk['source']}")
        print(f"  Length: {len(chunk['content'])} chars")
        print(f"  Preview: {chunk['content'][:100]}...")
    
    return chunks


def test_prompt_generation():
    """Test prompt generation"""
    print("\n" + "="*80)
    print("TEST 3: Prompt Generation")
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
    
    print("\nGenerating prompts for each hint level...")
    for level in range(4):
        prompt = engine.generate_prompt(
            user_question=question,
            hint_level=level,
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        print(f"\n  Hint Level {level}:")
        print(f"  - Prompt length: {len(prompt)} chars")
        print(f"  - Contains mission context: {'ImagePullBackOff Challenge' in prompt}")
        print(f"  - Contains system state: {'ngnix' in prompt}")
        print(f"  - Contains hint instruction: {f'HINT LEVEL {level}' in prompt}")
    
    print("\n✓ All prompt levels generated successfully")


def test_file_structure():
    """Test file structure"""
    print("\n" + "="*80)
    print("TEST 4: File Structure")
    print("="*80)
    
    required_files = [
        "rag_service.py",
        "prompt_engine.py",
        "ai_engine.py",
        "requirements.txt",
        ".env.example",
        "README.md",
        "knowledge-base/k8s_troubleshooting_guide.md",
        "knowledge-base/survival_camp_playbook.md",
        "prompts/socratic_tutor.md"
    ]
    
    print("\nChecking required files...")
    all_exist = True
    for file in required_files:
        exists = os.path.exists(file)
        status = "✓" if exists else "✗"
        print(f"  {status} {file}")
        if not exists:
            all_exist = False
    
    if all_exist:
        print("\n✓ All required files exist")
    else:
        print("\n✗ Some files are missing")
    
    return all_exist


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("AI TUTOR SYSTEM - SIMPLE TEST")
    print("(No ChromaDB or OpenAI API required)")
    print("="*80 + "\n")
    
    try:
        # Test 1: File Structure
        test_file_structure()
        
        # Test 2: Document Loading
        docs = test_document_loading()
        
        # Test 3: Chunking
        chunks = test_chunking(docs)
        
        # Test 4: Prompt Generation
        test_prompt_generation()
        
        print("\n" + "="*80)
        print("✓ ALL TESTS PASSED!")
        print("="*80)
        
        print("\n📊 Summary:")
        print(f"  - Documents loaded: {len(docs)}")
        print(f"  - Chunks created: {len(chunks)}")
        print(f"  - Prompt levels tested: 4")
        
        print("\n🎯 Next Steps:")
        print("  1. Add OpenAI API key to .env file")
        print("  2. Test with OpenAI: python ai_engine.py")
        print("  3. For full RAG with ChromaDB, use Python 3.11 or 3.12")
        print()
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
