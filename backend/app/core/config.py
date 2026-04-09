from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Mission system
    CHAOS_BACKEND: str = "mock"  # "mock" | "chaos_mesh"
    VALIDATION_BACKEND: str = "mock"  # "mock" | "prometheus"
    PROMETHEUS_URL: str = "http://localhost:9090"
    MOCK_VALIDATION_AUTO_PASS: bool = False

    # AI Tutor
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_BACKEND: str = "mock"  # "mock" | "openai"
    CHROMA_PERSIST_DIR: str = "../ai-data/vector-db/chroma_data"
    KNOWLEDGE_BASE_DIR: str = "../ai-data/knowledge-base"

    class Config:
        env_file = ".env"


settings = Settings()
