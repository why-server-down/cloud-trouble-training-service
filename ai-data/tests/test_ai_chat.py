"""
AI Chat Test - Shows how AI would respond at different hint levels
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_engine import SocraticPromptEngine, MissionContext, SystemContext, UserContext


def test_ai_responses():
    """Test AI responses at different hint levels"""
    print("\n" + "="*80)
    print("🤖 AI CHAT TEST - Simulated Responses")
    print("="*80)
    
    # Initialize
    engine = SocraticPromptEngine()
    
    # Create contexts
    mission = MissionContext(
        mission_id="demo-1",
        mission_name="ImagePullBackOff Challenge",
        mission_level=1,
        chaos_type="image_pull_error",
        expected_solution="Fix image name typo"
    )
    
    system = SystemContext(
        namespace="user-demo",
        pod_status="ImagePullBackOff",
        pod_logs="Error: Failed to pull image 'ngnix:latest': rpc error: code = NotFound",
        recent_events="Warning  Failed     2m    kubelet  Failed to pull image 'ngnix:latest'"
    )
    
    user = UserContext(
        user_id="demo-user",
        hint_count=0,
        previous_questions=[]
    )
    
    # Display scenario
    print("\n📚 Scenario:")
    print(f"   Mission: {mission.mission_name}")
    print(f"   Pod Status: {system.pod_status}")
    print(f"   Error: {system.pod_logs[:80]}...")
    
    # Test questions and expected responses
    test_cases = [
        {
            "hint_level": 0,
            "question": "My pod is not starting. What should I check?",
            "expected_style": "General direction - Ask guiding questions",
            "example_response": """
🤖 AI Tutor (Level 0 - General Direction):

I see your pod isn't starting. Let's think about this systematically.

When a pod fails to start, there are usually a few key areas to investigate:
- What does the pod's status tell you?
- Are there any error messages in the logs?
- What events has Kubernetes recorded?

Can you tell me what you observe when you check the pod's current state?
What information do you see that might give us a clue?
"""
        },
        {
            "hint_level": 1,
            "question": "I see ImagePullBackOff error. What does that mean?",
            "expected_style": "Specific investigation - Point to areas",
            "example_response": """
🤖 AI Tutor (Level 1 - Specific Investigation):

Good observation! ImagePullBackOff means Kubernetes is having trouble pulling the container image.

This error specifically indicates:
- The image name or tag might be incorrect
- The image might not exist in the registry
- There could be authentication issues

Looking at your pod's error message, I notice it's trying to pull 'ngnix:latest'.
Take a close look at that image name. Does anything seem unusual about it?

Try examining the pod's configuration to see exactly what image is specified.
"""
        },
        {
            "hint_level": 2,
            "question": "How do I check the image name?",
            "expected_style": "Exact commands - Provide kubectl commands",
            "example_response": """
🤖 AI Tutor (Level 2 - Exact Commands):

Great question! Here's how to check the image configuration:

1. First, describe the pod to see its full configuration:
   kubectl describe pod <pod-name> -n user-demo

2. Look for the "Image:" field in the output. You'll see what image is configured.

3. You can also check the deployment or pod YAML:
   kubectl get pod <pod-name> -n user-demo -o yaml

In the output, look at the error message carefully. Compare the image name
'ngnix:latest' with the correct nginx image name. Do you spot the typo?

Once you find it, you'll need to edit the resource that created this pod.
"""
        },
        {
            "hint_level": 3,
            "question": "I found the typo. How do I fix it?",
            "expected_style": "Complete solution - Full step-by-step",
            "example_response": """
🤖 AI Tutor (Level 3 - Complete Solution):

Perfect! You found the typo: 'ngnix' should be 'nginx' (the 'i' and 'n' are swapped).

Here's the complete fix:

1. Edit the deployment (or pod):
   kubectl edit deployment <deployment-name> -n user-demo

2. Find the line with the image:
   image: ngnix:latest

3. Change it to:
   image: nginx:latest

4. Save and exit the editor (in vi: press ESC, type :wq, press ENTER)

5. Kubernetes will automatically:
   - Create a new pod with the correct image
   - Terminate the old pod
   - Pull the nginx:latest image successfully

6. Verify the fix:
   kubectl get pods -n user-demo
   
   You should see the pod status change to "Running" within a minute.

Why this works:
- 'nginx' is the official NGINX image on Docker Hub
- The typo 'ngnix' doesn't exist, causing the ImagePullBackOff error
- Kubernetes automatically applies the corrected configuration
"""
        }
    ]
    
    # Display each test case
    for i, test in enumerate(test_cases, 1):
        print("\n" + "="*80)
        print(f"Test Case {i}: Hint Level {test['hint_level']}")
        print("="*80)
        print(f"\nGuidance Style: {test['expected_style']}")
        print(f"\n👤 Student: \"{test['question']}\"")
        print(test['example_response'])
        
        # Generate actual prompt
        prompt = engine.generate_prompt(
            user_question=test['question'],
            hint_level=test['hint_level'],
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        
        print(f"\n📊 Prompt Stats:")
        print(f"   - Length: {len(prompt)} characters")
        print(f"   - Estimated tokens: ~{len(prompt.split())}")
        print(f"   - Contains mission context: ✓")
        print(f"   - Contains system logs: ✓")
        print(f"   - Hint level instruction: Level {test['hint_level']}")
        
        # Update user context
        user.hint_count += 1
        user.previous_questions.append(test['question'])
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print("\n✅ Demonstrated AI Tutor Behavior:")
    print("   • Level 0: Asks guiding questions, no specific commands")
    print("   • Level 1: Points to specific areas to investigate")
    print("   • Level 2: Provides exact kubectl commands")
    print("   • Level 3: Gives complete solution with explanation")
    
    print("\n✅ Prompt Generation:")
    print("   • System prompt loaded from file")
    print("   • Hint level instructions applied")
    print("   • Mission and system context included")
    print("   • User history tracked")
    
    print("\n💡 To test with real OpenAI API:")
    print("   1. Add your API key to .env file:")
    print("      OPENAI_API_KEY=sk-your-actual-key")
    print("   2. Run: python chat_demo.py")
    print("   3. Chat with the AI tutor interactively!")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    test_ai_responses()
