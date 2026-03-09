"""
Prompt Engine for Socratic Tutoring
Generates context-aware prompts based on hint levels
"""

import os
from typing import Dict, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class MissionContext:
    """Mission information"""
    mission_id: str
    mission_name: str
    mission_level: int
    chaos_type: str
    expected_solution: str


@dataclass
class SystemContext:
    """Kubernetes system state"""
    namespace: str
    pod_status: str
    pod_logs: str
    recent_events: str


@dataclass
class UserContext:
    """User history and progress"""
    user_id: str
    hint_count: int
    previous_questions: list


class SocraticPromptEngine:
    """
    Generates prompts using Socratic method
    Adjusts guidance based on hint level
    """
    
    def __init__(self, system_prompt_path: str = "./prompts/socratic_tutor.md"):
        """Initialize with system prompt"""
        self.system_prompt = self._load_system_prompt(system_prompt_path)
        
        self.hint_level_instructions = {
            0: """
HINT LEVEL 0 - Directional Guidance:
- Provide ONLY general direction
- Ask questions about what they can observe
- DO NOT mention specific commands, resource names, or solutions
- Guide them to think about WHERE to look, not WHAT to do
- Example: "What does the pod's status tell you? What might cause that?"
""",
            1: """
HINT LEVEL 1 - Specific Investigation:
- Point to specific resources or log sections to check
- Suggest the TYPE of kubectl command (describe, logs, get)
- DO NOT provide exact command syntax yet
- Example: "Check the pod's detailed information and events. What error appears in the events?"
""",
            2: """
HINT LEVEL 2 - Exact Commands:
- Provide specific kubectl commands with exact syntax
- Tell them what to look for in the output
- Explain what the command does
- Example: "Run `kubectl describe pod <pod-name>` and look at the Events section at the bottom. What error message do you see there?"
""",
            3: """
HINT LEVEL 3 - Complete Solution:
- Provide the full solution with step-by-step instructions
- Include exact commands and any YAML edits needed
- Explain WHY each step is necessary
- Example: "The issue is a typo in the image name. Here's how to fix it:
  1. Edit the deployment: `kubectl edit deployment <name>`
  2. Find the image line (around line 24)
  3. Change 'ngnix' to 'nginx'
  4. Save and exit. The pod will automatically restart with the correct image."
"""
        }
    
    def _load_system_prompt(self, path: str) -> str:
        """Load system prompt from file"""
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return "You are a helpful Kubernetes tutor."
    
    def generate_prompt(
        self,
        user_question: str,
        hint_level: int = 0,
        mission_ctx: Optional[MissionContext] = None,
        system_ctx: Optional[SystemContext] = None,
        user_ctx: Optional[UserContext] = None,
        retrieved_docs: Optional[str] = None
    ) -> str:
        """
        Generate complete prompt for LLM
        
        Args:
            user_question: User's question
            hint_level: Current hint level (0-3)
            mission_ctx: Mission information
            system_ctx: K8s system state
            user_ctx: User history
            retrieved_docs: RAG retrieved documentation
        
        Returns:
            Complete prompt string
        """
        prompt_parts = [self.system_prompt]
        
        # Add hint level instruction
        prompt_parts.append(self.hint_level_instructions.get(hint_level, ""))
        
        # Add mission context
        if mission_ctx:
            prompt_parts.append(self._format_mission_context(mission_ctx))
        
        # Add system context
        if system_ctx:
            prompt_parts.append(self._format_system_context(system_ctx))
        
        # Add user context
        if user_ctx:
            prompt_parts.append(self._format_user_context(user_ctx))
        
        # Add retrieved documentation
        if retrieved_docs:
            prompt_parts.append(retrieved_docs)
        
        # Add user question
        prompt_parts.append(f"\n\n=== USER QUESTION ===\n{user_question}\n")
        
        # Add response instruction
        prompt_parts.append("""
=== YOUR RESPONSE ===
Provide your Socratic guidance below. Remember to:
1. Stay within your assigned hint level
2. Ask guiding questions
3. Reference the context provided
4. Be encouraging and supportive
""")
        
        return "\n".join(prompt_parts)

    
    def _format_mission_context(self, ctx: MissionContext) -> str:
        """Format mission context for prompt"""
        return f"""
=== MISSION CONTEXT ===
Mission: {ctx.mission_name} (Level {ctx.mission_level})
Mission ID: {ctx.mission_id}
Chaos Type: {ctx.chaos_type}
Expected Solution Category: {ctx.expected_solution}

Note: Guide the student toward understanding this type of issue, but don't reveal the solution directly unless at hint level 3.
"""
    
    def _format_system_context(self, ctx: SystemContext) -> str:
        """Format system context for prompt"""
        return f"""
=== CURRENT SYSTEM STATE ===
Namespace: {ctx.namespace}
Pod Status: {ctx.pod_status}

Recent Pod Logs:
{ctx.pod_logs}

Recent Events:
{ctx.recent_events}

Use this information to provide context-aware guidance. Reference specific observations from these logs and events.
"""
    
    def _format_user_context(self, ctx: UserContext) -> str:
        """Format user context for prompt"""
        previous_q = "\n".join(ctx.previous_questions[-3:]) if ctx.previous_questions else "None"
        
        return f"""
=== USER CONTEXT ===
User ID: {ctx.user_id}
Hints Used: {ctx.hint_count}
Recent Questions:
{previous_q}

Consider their previous questions to avoid repeating information and to build on their learning journey.
"""


def main():
    """Example usage of prompt engine"""
    engine = SocraticPromptEngine()
    
    # Example contexts
    mission = MissionContext(
        mission_id="m1",
        mission_name="ImagePullBackOff Challenge",
        mission_level=1,
        chaos_type="image_pull_error",
        expected_solution="Fix image name typo"
    )
    
    system = SystemContext(
        namespace="user-123",
        pod_status="ImagePullBackOff",
        pod_logs="Error: Failed to pull image 'ngnix:latest'",
        recent_events="Failed to pull image 'ngnix:latest': rpc error: code = NotFound"
    )
    
    user = UserContext(
        user_id="user-123",
        hint_count=1,
        previous_questions=["Why is my pod not starting?"]
    )
    
    # Generate prompts at different hint levels
    for level in range(4):
        print(f"\n{'='*80}")
        print(f"HINT LEVEL {level}")
        print('='*80)
        
        prompt = engine.generate_prompt(
            user_question="My pod is stuck in ImagePullBackOff. What should I do?",
            hint_level=level,
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        
        print(prompt[:500] + "...\n")


if __name__ == "__main__":
    main()
