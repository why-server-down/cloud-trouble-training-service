from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival"
    # 스키마의 단일 출처는 Alembic 마이그레이션이다.
    # 로컬 개발/테스트 편의를 위해서만 startup 시 create_all 을 허용하고,
    # 배포 환경에서는 False 로 두고 `alembic upgrade head` 를 배포 단계에서 실행한다.
    AUTO_CREATE_SCHEMA: bool = True
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Mission system
    CHAOS_BACKEND: str = "mock"  # "mock" | "chaos_mesh"
    VALIDATION_BACKEND: str = "mock"  # "mock" | "k8s" | "prometheus"
    PROMETHEUS_URL: str = "http://localhost:9090"
    MOCK_VALIDATION_AUTO_PASS: bool = False
    DEMO_UNLOCK_AI_SCENARIOS: bool = False

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
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    KNOWLEDGE_BASE_DIR: str = "../ai-data/knowledge-base"

    class Config:
        env_file = ".env"


settings = Settings()
