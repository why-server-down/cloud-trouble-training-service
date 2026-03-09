"""
Interactive Chat Demo for AI Tutor System
Simple command-line interface to test the AI tutor
"""

import sys
import os
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import LLMClient, LLMClientError
from prompt_engine import SocraticPromptEngine, MissionContext, SystemContext, UserContext
from config import config


class ChatDemo:
    """Simple chat interface for testing AI tutor"""
    
    def __init__(self):
        """Initialize chat demo"""
        self.prompt_engine = SocraticPromptEngine()
        self.llm_client = None
        self.hint_level = 0
        self.conversation_history = []
        
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
    
    def initialize_llm(self) -> bool:
        """Initialize LLM client"""
        try:
            self.llm_client = LLMClient()
            return True
        except LLMClientError as e:
            print(f"❌ Failed to initialize LLM: {str(e)}")
            return False
    
    def display_welcome(self):
        """Display welcome message"""
        print("\n" + "="*80)
        print("🤖 AI TUTOR CHAT DEMO")
        print("="*80)
        print("\n📚 Current Mission:")
        print(f"   {self.mission.mission_name} (Level {self.mission.mission_level})")
        print(f"\n🔍 System Status:")
        print(f"   Namespace: {self.system.namespace}")
        print(f"   Pod Status: {self.system.pod_status}")
        print(f"\n💡 Hint Level: {self.hint_level}")
        print("   - Level 0: General direction")
        print("   - Level 1: Specific investigation")
        print("   - Level 2: Exact commands")
        print("   - Level 3: Complete solution")
        print("\n📝 Commands:")
        print("   /hint     - Increase hint level")
        print("   /reset    - Reset hint level to 0")
        print("   /status   - Show current status")
        print("   /quit     - Exit chat")
        print("="*80 + "\n")
    
    def display_status(self):
        """Display current status"""
        print("\n" + "="*80)
        print("📊 CURRENT STATUS")
        print("="*80)
        print(f"Mission: {self.mission.mission_name}")
        print(f"Hint Level: {self.hint_level}")
        print(f"Hints Used: {self.user.hint_count}")
        print(f"Questions Asked: {len(self.user.previous_questions)}")
        print(f"Pod Status: {self.system.pod_status}")
        print("="*80 + "\n")
    
    def increase_hint_level(self):
        """Increase hint level"""
        if self.hint_level < 3:
            self.hint_level += 1
            self.user.hint_count += 1
            print(f"\n💡 Hint level increased to {self.hint_level}")
            
            penalties = {1: 5, 2: 10, 3: 50}
            penalty = penalties.get(self.hint_level, 0)
            if penalty > 0:
                print(f"   Points deducted: -{penalty}")
        else:
            print("\n⚠️  Already at maximum hint level (3)")
    
    def reset_hint_level(self):
        """Reset hint level"""
        self.hint_level = 0
        print("\n🔄 Hint level reset to 0")
    
    def get_ai_response(self, user_question: str) -> Optional[str]:
        """Get AI response"""
        if not self.llm_client:
            return None
        
        try:
            # Generate prompt
            prompt = self.prompt_engine.generate_prompt(
                user_question=user_question,
                hint_level=self.hint_level,
                mission_ctx=self.mission,
                system_ctx=self.system,
                user_ctx=self.user
            )
            
            # Get LLM response
            print("\n🤔 AI is thinking...")
            response = self.llm_client.generate(
                prompt=prompt,
                max_tokens=500
            )
            
            # Update conversation history
            self.conversation_history.append({
                "user": user_question,
                "assistant": response.content,
                "hint_level": self.hint_level,
                "tokens": response.total_tokens
            })
            
            # Update user context
            self.user.previous_questions.append(user_question)
            
            return response.content
        
        except Exception as e:
            print(f"\n❌ Error getting AI response: {str(e)}")
            return None
    
    def run(self):
        """Run chat demo"""
        # Check configuration
        if not config.validate():
            print("\n❌ Configuration invalid!")
            print("💡 Please set OPENAI_API_KEY in .env file")
            print("\nExample:")
            print("  OPENAI_API_KEY=sk-your-actual-api-key-here")
            return
        
        # Initialize LLM
        print("\n🔧 Initializing AI Tutor...")
        if not self.initialize_llm():
            return
        
        print("✅ AI Tutor initialized successfully!")
        
        # Display welcome
        self.display_welcome()
        
        # Chat loop
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
                        print("\n👋 Goodbye! Thanks for testing the AI Tutor!")
                        break
                    
                    elif command == '/hint':
                        self.increase_hint_level()
                        continue
                    
                    elif command == '/reset':
                        self.reset_hint_level()
                        continue
                    
                    elif command == '/status':
                        self.display_status()
                        continue
                    
                    elif command == '/help':
                        print("\n📝 Available commands:")
                        print("   /hint     - Increase hint level")
                        print("   /reset    - Reset hint level to 0")
                        print("   /status   - Show current status")
                        print("   /help     - Show this help")
                        print("   /quit     - Exit chat\n")
                        continue
                    
                    else:
                        print(f"\n❓ Unknown command: {command}")
                        print("   Type /help for available commands\n")
                        continue
                
                # Get AI response
                response = self.get_ai_response(user_input)
                
                if response:
                    print(f"\n🤖 AI Tutor (Hint Level {self.hint_level}):")
                    print(f"{response}\n")
                else:
                    print("\n❌ Failed to get AI response\n")
            
            except KeyboardInterrupt:
                print("\n\n👋 Chat interrupted. Goodbye!")
                break
            
            except Exception as e:
                print(f"\n❌ Error: {str(e)}\n")
        
        # Display summary
        if self.conversation_history:
            print("\n" + "="*80)
            print("📊 CHAT SUMMARY")
            print("="*80)
            print(f"Total questions: {len(self.conversation_history)}")
            print(f"Hints used: {self.user.hint_count}")
            print(f"Final hint level: {self.hint_level}")
            
            total_tokens = sum(msg['tokens'] for msg in self.conversation_history)
            print(f"Total tokens used: {total_tokens}")
            print("="*80 + "\n")


def main():
    """Main entry point"""
    demo = ChatDemo()
    demo.run()


if __name__ == "__main__":
    main()
