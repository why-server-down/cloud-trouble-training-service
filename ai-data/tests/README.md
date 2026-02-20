# AI Tutor Tests & Demos

This directory contains test files and demo scripts for the AI Tutor system.

## Test Files

### Unit Tests
- `test_basic.py` - Basic configuration and setup tests
- `test_rag.py` - RAG service tests
- `test_simple.py` - Simple functionality tests
- `test_task1.py` - Task 1 (LLM setup) tests

### Demo Scripts
- `chat_demo.py` - Interactive chat with real OpenAI API
- `chat_demo_offline.py` - Offline demo showing prompt generation
- `simple_chat_test.py` - Simple chat test with simulated responses
- `test_ai_chat.py` - AI chat behavior demonstration

### Utilities
- `run_simple_test.bat` - Batch script to run simple tests

## Running Tests

### Prerequisites
Make sure you're in the ai-data directory and have activated the virtual environment:
```bash
cd ai-data
venv\Scripts\activate  # Windows
```

### Run Individual Tests
```bash
# Basic tests
python tests/test_basic.py

# RAG tests
python tests/test_rag.py

# Task 1 tests
python tests/test_task1.py
```

### Run Demos

#### Offline Demo (No API Key Required)
```bash
python tests/chat_demo_offline.py
```
Shows how prompts are generated at different hint levels without calling OpenAI API.

#### Simple Chat Test (No API Key Required)
```bash
python tests/simple_chat_test.py
```
Displays simulated AI responses at all hint levels.

#### Interactive Chat Demo (Requires API Key)
```bash
python tests/chat_demo.py
```
Chat with the real AI tutor. Requires `OPENAI_API_KEY` in `.env` file.

Commands:
- `/hint` - Increase hint level
- `/reset` - Reset hint level to 0
- `/status` - Show current status
- `/quit` - Exit chat

## Test Coverage

✅ Configuration loading and validation
✅ Prompt engine with 4 hint levels
✅ LLM client with retry logic
✅ Context management (Mission, System, User)
✅ Socratic method implementation
✅ Interactive chat interface

## Notes

- Test files import from parent directory (`../`)
- Demos use sample mission context (ImagePullBackOff Challenge)
- All tests can run without external dependencies except chat_demo.py
