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

    # 샌드박스 (BE-04)
    # 이미지는 shell 을 포함해야 한다. toolbox Pod 가 /bin/sh 로 유지되기 때문이며,
    # distroless 계열(registry.k8s.io/kubectl 등)은 쓸 수 없다.
    # 클러스터와 kubectl 마이너 버전을 맞춘다.
    SANDBOX_TOOLBOX_IMAGE: str = "alpine/k8s:1.34.1"
    SANDBOX_READINESS_TIMEOUT_SECONDS: float = 90.0
    # Docker 환경 샌드박스(DinD). rootless 가 클러스터에서 기동하지 않아 privileged 를 쓰며,
    # 대신 자원 상한과 네트워크 정책으로 범위를 좁힌다. 자세한 사유는 sandbox_service 참고.
    SANDBOX_DIND_IMAGE: str = "docker:27-dind"
    SANDBOX_DIND_CPU_LIMIT: str = "1"
    SANDBOX_DIND_MEMORY_LIMIT: str = "1Gi"
    SANDBOX_DIND_STORAGE_LIMIT: str = "2Gi"
    # DinD 안에서 훈련 대상이 되는 컨테이너
    SANDBOX_TRAINING_IMAGE: str = "nginx:alpine"
    SANDBOX_TRAINING_CONTAINER: str = "training-app"
    SANDBOX_TRAINING_NETWORK: str = "training-net"
    SANDBOX_TRAINING_VOLUME: str = "training-data"
    SANDBOX_TRAINING_CPUS: str = "1"   # 훈련 컨테이너 정상 상태의 CPU 상한

    # Linux 환경 샌드박스. 관측 도구가 미리 들어 있는 이미지를 쓴다.
    # (실측: journalctl/systemctl 은 systemd 부재로, dmesg 는 커널 버퍼 접근 제한으로
    #  어떤 이미지에서도 동작하지 않는다. 그래서 명령 정책에서 제외한다)
    SANDBOX_LINUX_IMAGE: str = "nicolaka/netshoot:v0.13"
    SANDBOX_LINUX_CPU_LIMIT: str = "500m"
    SANDBOX_LINUX_MEMORY_LIMIT: str = "512Mi"
    SANDBOX_LINUX_STORAGE_LIMIT: str = "1Gi"
    SANDBOX_LINUX_PID_LIMIT: int = 256
    # 훈련 작업 디렉터리. tmpfs 로 마운트해 크기 상한이 df 에 보이게 한다.
    # ephemeral-storage 상한은 kubelet 검사용이라 컨테이너 안 df 에 나타나지 않아
    # 사용자가 디스크 압박을 관측할 수 없다.
    SANDBOX_LINUX_WORKDIR: str = "/tmp/afterfail"
    SANDBOX_LINUX_WORKDIR_SIZE: str = "64Mi"

    # Chaos Mesh 가 설치된 네임스페이스.
    # 공식 helm chart 기본값은 chaos-mesh 이고, 구버전 문서의 chaos-testing 과 다르다.
    # 클러스터마다 다를 수 있어 설정으로 둔다.
    CHAOS_MESH_NAMESPACE: str = "chaos-mesh"

    # RuntimeContext 수집 (BE-19)
    # 부분 실패를 허용하므로, 느린 수집 하나가 튜터 응답 전체를 붙잡지 않게 한다.
    RUNTIME_CONTEXT_TIMEOUT_SECONDS: float = 3.0

    # 환경별 분석 (BE-21)
    # competency 의 speed 항이 기준으로 삼는 목표 복구 시간(초).
    # 미션 time_limit 이 환경마다 다르므로 환경별 대표값을 설정으로 둔다.
    TARGET_MTTR_SECONDS: int = 900

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
