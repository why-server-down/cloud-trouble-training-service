"""
Offline Chat Demo - No API Key Required
Shows how prompts are generated without calling OpenAI API
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_engine import SocraticPromptEngine, MissionContext, SystemContext, UserContext


class OfflineChatDemo:
    """Offline chat demo - shows prompts without API calls"""
    
    def __init__(self):
        """Initialize offline demo"""
        self.prompt_engine = SocraticPromptEngine()
        self.hint_level = 0
        
        # Sample mission context
        self.mission = MissionContext(
            mission_id="demo-1",
            mission_name="ImagePullBackOff Challenge",
            mission_level=1,
            chaos_type="image_pull_error",
            expected_solution="Fix image name typo"
        )
        
        # Sample system context
        self.system = SystemContext(
            namespace="user-demo",
            pod_status="ImagePullBackOff",
            pod_logs="Error: Failed to pull image 'ngnix:latest': rpc error: code = NotFound",
            recent_events="Warning  Failed     2m    kubelet  Failed to pull image 'ngnix:latest'"
        )
        
        # User context
        self.user = UserContext(
            user_id="demo-user",
            hint_count=0,
            previous_questions=[]
        )
    
    def display_welcome(self):
        """Display welcome message"""
        print("\n" + "="*80)
        print("🤖 AI TUTOR OFFLINE DEMO (No API Key Required)")
        print("="*80)
        print("\n📚 Current Mission:")
        print(f"   {self.mission.mission_name} (Level {self.mission.mission_level})")
        print(f"\n🔍 System Status:")
        print(f"   Namespace: {self.system.namespace}")
        print(f"   Pod Status: {self.system.pod_status}")
        print(f"   Logs: {self.system.pod_logs[:80]}...")
        print(f"\n💡 Current Hint Level: {self.hint_level}")
        print("\n📝 Commands:")
        print("   /hint     - Increase hint level and see how prompt changes")
        print("   /reset    - Reset hint level to 0")
        print("   /quit     - Exit demo")
        print("\n💬 Type your question to see the generated prompt!")
        print("="*80 + "\n")
    
    def show_prompt(self, user_question: str):
        """Show generated prompt"""
        prompt = self.prompt_engine.generate_prompt(
            user_question=user_question,
            hint_level=self.hint_level,
            mission_ctx=self.mission,
            system_ctx=self.system,
            user_ctx=self.user
        )
        
        print("\n" + "="*80)
        print(f"📝 GENERATED PROMPT (Hint Level {self.hint_level})")
        print("="*80)
        print(prompt)
        print("="*80)
        print(f"\nPrompt length: {len(prompt)} characters")
        print(f"Estimated tokens: ~{len(prompt.split())}")
        print("\n💡 This prompt would be sent to OpenAI API")
        print("="*80 + "\n")
        
        # Update user context
        self.user.previous_questions.append(user_question)
    
    def increase_hint_level(self):
        """Increase hint level"""
        if self.hint_level < 3:
            self.hint_level += 1
            self.user.hint_count += 1
            print(f"\n💡 Hint level increased to {self.hint_level}")
            
            penalties = {1: 5, 2: 10, 3: 50}
            penalty = penalties.get(self.hint_level, 0)
            if penalty > 0:
                print(f"   Points would be deducted: -{penalty}")
            
            # Show what changes at this level
            level_descriptions = {
                0: "General direction only",
                1: "Specific area to investigate",
                2: "Exact commands to run",
                3: "Complete solution with explanation"
            }
            print(f"   Guidance style: {level_descriptions[self.hint_level]}")
        else:
            print("\n⚠️  Already at maximum hint level (3)")
    
    def reset_hint_level(self):
        """Reset hint level"""
        self.hint_level = 0
        print("\n🔄 Hint level reset to 0")
    
    def run(self):
        """Run offline demo"""
        self.display_welcome()
        
        # Demo loop
        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith('/'):
                    command = user_input.lower()
                    
                    if command == '/quit' or command == '/exit':
                        print("\n👋 Goodbye!")
                        break
                    
                    elif command == '/hint':
                        self.increase_hint_level()
                        continue
                    
                    elif command == '/reset':
                        self.reset_hint_level()
                        continue
                    
                    elif command == '/help':
                        print("\n📝 Available commands:")
                        print("   /hint     - Increase hint level")
                        print("   /reset    - Reset hint level to 0")
                        print("   /help     - Show this help")
                        print("   /quit     - Exit demo\n")
                        continue
                    
                    else:
                        print(f"\n❓ Unknown command: {command}")
                        print("   Type /help for available commands\n")
                        continue
                
                # Show generated prompt
                self.show_prompt(user_input)
            
            except KeyboardInterrupt:
                print("\n\n👋 Demo interrupted. Goodbye!")
                break
            
            except Exception as e:
                print(f"\n❌ Error: {str(e)}\n")
        
        # Display summary
        print("\n" + "="*80)
        print("📊 DEMO SUMMARY")
        print("="*80)
        print(f"Questions asked: {len(self.user.previous_questions)}")
        print(f"Hints used: {self.user.hint_count}")
        print(f"Final hint level: {self.hint_level}")
        print("\n💡 To test with real AI responses:")
        print("   1. Add your OpenAI API key to .env file")
        print("   2. Run: python chat_demo.py")
        print("="*80 + "\n")


def main():
    """Main entry point"""
    print("\n🎯 This demo shows how prompts are generated")
    print("   No OpenAI API key required!")
    
    demo = OfflineChatDemo()
    demo.run()


if __name__ == "__main__":
    main()
