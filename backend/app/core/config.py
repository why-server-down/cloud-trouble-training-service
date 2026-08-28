from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival"
    # 스키마의 단일 출처는 Alembic 마이그레이션이다.
    # 로컬 개발/테스트 편의를 위해서만 startup 시 create_all 을 허용하고,
    # 배포 환경에서는 False 로 두고 `alembic upgrade head` 를 배포 단계에서 실행한다.
    AUTO_CREATE_SCHEMA: bool = True
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Terminal 실행 (BE-05)
    # 사용자 명령은 호스트 셸이 아니라 사용자 네임스페이스의 샌드박스 Pod 안에서 실행된다.
    TERMINAL_BACKEND: str = "sandbox"  # "sandbox" | "mock"
    COMMAND_TIMEOUT_SECONDS: int = 5
    COMMAND_TIMEOUT_MAX_SECONDS: int = 30  # 환경별 override 상한
    COMMAND_OUTPUT_LIMIT_BYTES: int = 64 * 1024  # 사용자에게 보내는 출력 상한
    COMMAND_LOG_LIMIT_BYTES: int = 5 * 1024  # CommandLog 에 저장하는 상한

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

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
