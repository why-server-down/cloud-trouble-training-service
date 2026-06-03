# AI Tutor System - Tasks

## Phase 1: Infrastructure Setup

### Task 1: LLM Integration
- [ ] 1.1 Install LangChain and OpenAI SDK
- [ ] 1.2 Configure OpenAI API key
- [ ] 1.3 Create LLM client wrapper
- [ ] 1.4 Test API connectivity
- [ ] 1.5 Add retry logic

### Task 2: Vector Database Setup
- [ ] 2.1 Install ChromaDB
- [ ] 2.2 Configure ChromaDB client
- [ ] 2.3 Create collection for K8s docs
- [ ] 2.4 Test vector storage
- [ ] 2.5 Add error handling

### Task 3: Database Schema
- [ ] 3.1 Create Conversation table
- [ ] 3.2 Create Message table
- [ ] 3.3 Create HintHistory table
- [ ] 3.4 Add indexes
- [ ] 3.5 Create migration scripts

## Phase 2: Context Collection

### Task 4: Mission Context Collection
- [ ] 4.1 Create MissionContext model
- [ ] 4.2 Implement mission info retrieval
- [ ] 4.3 Calculate time elapsed
- [ ] 4.4 Add caching
- [ ] 4.5 Test context collection

### Task 5: System Context Collection
- [ ] 5.1 Create SystemContext model
- [ ] 5.2 Implement pod status collection
- [ ] 5.3 Implement log collection (last 50 lines)
- [ ] 5.4 Implement event collection
- [ ] 5.5 Add 3-second timeout

### Task 6: User Context Collection
- [ ] 6.1 Create UserContext model
- [ ] 6.2 Implement hint history retrieval
- [ ] 6.3 Calculate previous attempts
- [ ] 6.4 Retrieve skill level
- [ ] 6.5 Test user context

### Task 7: Parallel Context Collection
- [ ] 7.1 Implement asyncio.gather for parallel execution
- [ ] 7.2 Combine all contexts into FullContext
- [ ] 7.3 Add timeout handling
- [ ] 7.4 Test performance (< 3 seconds)
- [ ] 7.5 Add error handling

## Phase 3: Prompt Engineering

### Task 8: Socratic Prompt Engine
- [ ] 8.1 Create SocraticPromptEngine class
- [ ] 8.2 Define system prompt template
- [ ] 8.3 Implement context formatting
- [ ] 8.4 Implement hint level instructions
- [ ] 8.5 Test prompt generation

### Task 9: Hint Level Logic
- [ ] 9.1 Define hint level 0 (direction)
- [ ] 9.2 Define hint level 1 (specific area)
- [ ] 9.3 Define hint level 2 (exact command)
- [ ] 9.4 Define hint level 3 (complete solution)
- [ ] 9.5 Test each hint level

### Task 10: Context Formatting
- [ ] 10.1 Format mission context for prompt
- [ ] 10.2 Format system context (pods, logs)
- [ ] 10.3 Format user context (history)
- [ ] 10.4 Keep prompt under token limit
- [ ] 10.5 Test formatted prompts

## Phase 4: RAG Implementation

### Task 11: Knowledge Base Preparation
- [ ] 11.1 Collect K8s official documentation
- [ ] 11.2 Collect troubleshooting guides
- [ ] 11.3 Split documents into chunks
- [ ] 11.4 Generate embeddings
- [ ] 11.5 Store in ChromaDB

### Task 12: RAG Service
- [ ] 12.1 Create RAGService class
- [ ] 12.2 Implement query embedding
- [ ] 12.3 Implement vector search
- [ ] 12.4 Filter by similarity threshold (0.7)
- [ ] 12.5 Test document retrieval

### Task 13: Prompt Augmentation
- [ ] 13.1 Implement prompt augmentation
- [ ] 13.2 Format retrieved documents
- [ ] 13.3 Add source citations
- [ ] 13.4 Ensure 2-second search timeout
- [ ] 13.5 Test augmented prompts

## Phase 5: Hint Management

### Task 14: Hint Level Manager
- [ ] 14.1 Create HintManager class
- [ ] 14.2 Define hint penalties
- [ ] 14.3 Implement hint request handler
- [ ] 14.4 Implement point deduction
- [ ] 14.5 Log hint usage

### Task 15: Auto-escalation Logic
- [ ] 15.1 Detect repetitive questions
- [ ] 15.2 Count failed attempts
- [ ] 15.3 Auto-escalate after 3 attempts
- [ ] 15.4 Notify user of escalation
- [ ] 15.5 Test auto-escalation

## Phase 6: Chat API

### Task 16: Chat Endpoint
- [ ] 16.1 Create ChatRequest model
- [ ] 16.2 Create ChatResponse model
- [ ] 16.3 Implement message endpoint
- [ ] 16.4 Add authentication
- [ ] 16.5 Test chat endpoint

### Task 17: Message Processing
- [ ] 17.1 Collect context on message
- [ ] 17.2 Check for auto-escalation
- [ ] 17.3 Generate prompt
- [ ] 17.4 Augment with RAG if needed
- [ ] 17.5 Call LLM API

### Task 18: Response Handling
- [ ] 18.1 Parse LLM response
- [ ] 18.2 Save user message to DB
- [ ] 18.3 Save assistant message to DB
- [ ] 18.4 Return response to client
- [ ] 18.5 Test complete flow

### Task 19: Hint Request Endpoint
- [ ] 19.1 Create HintRequest model
- [ ] 19.2 Create hint endpoint
- [ ] 19.3 Increment hint level
- [ ] 19.4 Deduct points
- [ ] 19.5 Test hint requests

## Phase 7: Performance Optimization

### Task 20: Caching Implementation
- [ ] 20.1 Cache mission context (5 min TTL)
- [ ] 20.2 Cache user skill level (10 min TTL)
- [ ] 20.3 Cache RAG embeddings (1 hour TTL)
- [ ] 20.4 Test cache hit rates
- [ ] 20.5 Monitor cache performance

### Task 21: Rate Limiting
- [ ] 21.1 Add rate limit to LLM calls (10/min)
- [ ] 21.2 Add rate limit to hint requests (5/5min)
- [ ] 21.3 Return proper error messages
- [ ] 21.4 Test rate limiting
- [ ] 21.5 Monitor rate limit hits

### Task 22: Error Handling
- [ ] 22.1 Handle context collection errors
- [ ] 22.2 Handle LLM API errors with retry
- [ ] 22.3 Handle RAG search errors
- [ ] 22.4 Add fallback responses
- [ ] 22.5 Test error scenarios

## Phase 8: Frontend Integration

### Task 23: Chat UI Component
- [ ] 23.1 Create chat interface component
- [ ] 23.2 Display message history
- [ ] 23.3 Add message input
- [ ] 23.4 Show typing indicator
- [ ] 23.5 Test chat UI

### Task 24: Hint Level UI
- [ ] 24.1 Create hint level selector
- [ ] 24.2 Show current hint level
- [ ] 24.3 Display point penalties
- [ ] 24.4 Add "More Hint" button
- [ ] 24.5 Test hint UI

### Task 25: Context Display
- [ ] 25.1 Show current mission info
- [ ] 25.2 Display pod status summary
- [ ] 25.3 Add expandable log viewer
- [ ] 25.4 Style context panel
- [ ] 25.5 Test context display

## Phase 9: Testing

### Task 26: Unit Testing
- [ ] 26.1 Test context collection
- [ ] 26.2 Test prompt generation
- [ ] 26.3 Test RAG search
- [ ] 26.4 Test hint management
- [ ] 26.5 Test caching

### Task 27: Integration Testing
- [ ] 27.1 Test complete chat flow
- [ ] 27.2 Test hint escalation
- [ ] 27.3 Test RAG integration
- [ ] 27.4 Test with real LLM
- [ ] 27.5 Test error handling

### Task 28: Property-Based Testing
- [ ] 28.1 Write PBT: AI never gives direct commands at level 0
- [ ] 28.2 Write PBT: Context collection < 3 seconds
- [ ] 28.3 Write PBT: RAG similarity >= 0.7
- [ ] 28.4 Write PBT: Hint penalties are correct
- [ ] 28.5 Run all property tests

## Phase 10: Prompt Refinement (Socratic Tutor Enhancement)

### Task 29: Hint Level Restructuring
- [x] 29.1 Remove Level 0 (consolidate 4-level to 3-level system)
- [x] 29.2 Redefine Level 1: Observation-focused guidance only
- [x] 29.3 Redefine Level 2: Technical concepts + log line hints (no direct cause)
- [x] 29.4 Redefine Level 3: Complete solution with YAML/commands
- [x] 29.5 Update penalty structure to match 3-level system

### Task 30: Prompt Template Enhancement
- [x] 30.1 Add context placeholder: {context}
- [x] 30.2 Add user message placeholder: {user_message}
- [x] 30.3 Add hint level placeholder: [Hint_Level]
- [x] 30.4 Define precise constraints for each level
- [x] 30.5 Update socratic_tutor.md with refined prompt

### Task 31: Level-Specific Constraint Definition
- [x] 31.1 Level 1 constraints: NO answers/causes, observation commands only
- [x] 31.2 Level 2 constraints: NO direct cause, explain concepts, hint at log lines
- [x] 31.3 Level 3 constraints: Provide complete YAML settings and exact commands
- [x] 31.4 Add examples for each level
- [x] 31.5 Validate constraint enforcement logic

### Task 32: Prompt Testing & Validation
- [ ] 32.1 Test Level 1: Verify no answers/causes are given
- [ ] 32.2 Test Level 2: Verify concept explanation without direct cause
- [ ] 32.3 Test Level 3: Verify complete solution is provided
- [ ] 32.4 Test context placeholder substitution
- [ ] 32.5 Validate with real Gemini API calls
