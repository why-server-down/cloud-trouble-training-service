from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Mission system
    CHAOS_BACKEND: str = "mock"  # "mock" | "chaos_mesh"
    VALIDATION_BACKEND: str = "mock"  # "mock" | "k8s" | "prometheus"
    PROMETHEUS_URL: str = "http://localhost:9090"
    MOCK_VALIDATION_AUTO_PASS: bool = False

    # AI Tutor & Scenario
    AI_BACKEND: str = "mock"  # "mock" | "openai" | "gemini"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    SCENARIO_MODEL: str = "gpt-4o-mini"
    TUTOR_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/text-embedding-004"

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    KNOWLEDGE_BASE_DIR: str = "../ai-data/knowledge-base"

    class Config:
        env_file = ".env"


settings = Settings()
