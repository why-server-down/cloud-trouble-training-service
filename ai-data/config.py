"""
Configuration management for AI Tutor System
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Configuration class for AI Tutor System"""

    # AI Backend: "mock" | "openai" | "gemini"
    AI_BACKEND: str = os.getenv("AI_BACKEND", "mock")

    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "500"))
    OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "10"))

    # Gemini Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")

    # Qdrant Configuration
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    
    # RAG Configuration
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "3"))
    RAG_MIN_SIMILARITY: float = float(os.getenv("RAG_MIN_SIMILARITY", "0.7"))
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
    
    # Performance Configuration
    CONTEXT_COLLECTION_TIMEOUT: int = int(os.getenv("CONTEXT_COLLECTION_TIMEOUT", "3"))
    RAG_SEARCH_TIMEOUT: int = int(os.getenv("RAG_SEARCH_TIMEOUT", "2"))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        if cls.AI_BACKEND == "gemini":
            if not cls.GEMINI_API_KEY:
                print("⚠️  Warning: GEMINI_API_KEY not set")
                return False
            return True
        if not cls.OPENAI_API_KEY:
            print("⚠️  Warning: OPENAI_API_KEY not set")
            return False
        if cls.OPENAI_API_KEY == "your_openai_api_key_here":
            print("⚠️  Warning: OPENAI_API_KEY is still the default value")
            return False
        return True
    
    @classmethod
    def display(cls):
        """Display current configuration (hide sensitive data)"""
        print("="*80)
        print("AI Tutor System Configuration")
        print("="*80)
        print(f"OpenAI Model: {cls.OPENAI_MODEL}")
        print(f"OpenAI Temperature: {cls.OPENAI_TEMPERATURE}")
        print(f"OpenAI Max Tokens: {cls.OPENAI_MAX_TOKENS}")
        print(f"OpenAI Timeout: {cls.OPENAI_TIMEOUT}s")
        print(f"OpenAI API Key: {'✓ Set' if cls.OPENAI_API_KEY and cls.OPENAI_API_KEY != 'your_openai_api_key_here' else '✗ Not Set'}")
        print()
        print(f"Qdrant URL: {cls.QDRANT_URL}")
        print()
        print(f"RAG Top K: {cls.RAG_TOP_K}")
        print(f"RAG Min Similarity: {cls.RAG_MIN_SIMILARITY}")
        print(f"RAG Chunk Size: {cls.RAG_CHUNK_SIZE}")
        print(f"RAG Chunk Overlap: {cls.RAG_CHUNK_OVERLAP}")
        print("="*80)


# Create global config instance
config = Config()


if __name__ == "__main__":
    config.display()
    
    if config.validate():
        print("\n✓ Configuration is valid")
    else:
        print("\n✗ Configuration is invalid")
