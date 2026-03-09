"""
Simple AI Chat Test - Shows simulated AI responses
"""

def show_ai_responses():
    """Show how AI would respond at different hint levels"""
    
    print("\n" + "="*80)
    print("🤖 AI TUTOR CHAT TEST")
    print("="*80)
    
    print("\n📚 Scenario:")
    print("   Mission: ImagePullBackOff Challenge (Level 1)")
    print("   Pod Status: ImagePullBackOff")
    print("   Error: Failed to pull image 'ngnix:latest'")
    
    # Test Case 1: Hint Level 0
    print("\n" + "="*80)
    print("Test 1: Hint Level 0 (General Direction)")
    print("="*80)
    print("\n👤 Student: \"My pod is not starting. What should I check?\"")
    print("\n🤖 AI Tutor:")
    print("""
I see your pod isn't starting. Let's think about this systematically.

When a pod fails to start, there are usually a few key areas to investigate:
- What does the pod's status tell you?
- Are there any error messages in the logs?
- What events has Kubernetes recorded?

Can you tell me what you observe when you check the pod's current state?
What information do you see that might give us a clue?
""")
    
    # Test Case 2: Hint Level 1
    print("\n" + "="*80)
    print("Test 2: Hint Level 1 (Specific Investigation)")
    print("="*80)
    print("\n👤 Student: \"I see ImagePullBackOff error. What does that mean?\"")
    print("\n🤖 AI Tutor:")
    print("""
Good observation! ImagePullBackOff means Kubernetes is having trouble 
pulling the container image.

This error specifically indicates:
- The image name or tag might be incorrect
- The image might not exist in the registry
- There could be authentication issues

Looking at your pod's error message, I notice it's trying to pull 'ngnix:latest'.
Take a close look at that image name. Does anything seem unusual about it?

Try examining the pod's configuration to see exactly what image is specified.
""")
    
    # Test Case 3: Hint Level 2
    print("\n" + "="*80)
    print("Test 3: Hint Level 2 (Exact Commands)")
    print("="*80)
    print("\n👤 Student: \"How do I check the image name?\"")
    print("\n🤖 AI Tutor:")
    print("""
Great question! Here's how to check the image configuration:

1. First, describe the pod to see its full configuration:
   kubectl describe pod <pod-name> -n user-demo

2. Look for the "Image:" field in the output.

3. You can also check the pod YAML:
   kubectl get pod <pod-name> -n user-demo -o yaml

In the output, look at the error message carefully. Compare the image name
'ngnix:latest' with the correct nginx image name. Do you spot the typo?

Once you find it, you'll need to edit the resource that created this pod.
""")
    
    # Test Case 4: Hint Level 3
    print("\n" + "="*80)
    print("Test 4: Hint Level 3 (Complete Solution)")
    print("="*80)
    print("\n👤 Student: \"I found the typo. How do I fix it?\"")
    print("\n🤖 AI Tutor:")
    print("""
Perfect! You found the typo: 'ngnix' should be 'nginx' (the 'i' and 'n' are swapped).

Here's the complete fix:

1. Edit the deployment:
   kubectl edit deployment <deployment-name> -n user-demo

2. Find the line with the image:
   image: ngnix:latest

3. Change it to:
   image: nginx:latest

4. Save and exit (in vi: press ESC, type :wq, press ENTER)

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
""")
    
    # Summary
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    print("""
✅ AI Tutor Behavior Demonstrated:
   • Level 0: Asks guiding questions, no specific commands
   • Level 1: Points to specific areas to investigate
   • Level 2: Provides exact kubectl commands
   • Level 3: Gives complete solution with explanation

✅ Socratic Method Implementation:
   • Progressively reveals information
   • Encourages student discovery
   • Adapts to student's needs
   • Maintains engagement through questions

💡 To test with REAL OpenAI API:
   1. Add your API key to .env file:
      OPENAI_API_KEY=sk-your-actual-key-here
   
   2. Run interactive chat:
      python chat_demo.py
   
   3. Chat with the AI tutor and see real responses!

📝 Current Status:
   ✓ Prompt engine working
   ✓ Hint level system implemented
   ✓ Context management ready
   ✓ LLM client configured
   
   ⏳ Waiting for: OpenAI API key to test real AI responses
""")
    print("="*80 + "\n")


if __name__ == "__main__":
    show_ai_responses()
