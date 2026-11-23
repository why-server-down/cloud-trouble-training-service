import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.environments import DEFAULT_ENVIRONMENT, SUPPORTED_ENVIRONMENTS

# environment 컬럼의 허용 값을 DB CHECK 제약으로도 강제한다.
# 애플리케이션(core/environments.py)과 DB가 같은 목록을 쓰도록 여기서 한 번만 만든다.
_ENVIRONMENT_VALUES = ", ".join(f"'{env}'" for env in SUPPORTED_ENVIRONMENTS)


def environment_check(table_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"environment IN ({_ENVIRONMENT_VALUES})",
        name=f"ck_{table_name}_environment",
    )


ATTEMPT_TYPES = ("static_mission", "ai_scenario")
_ATTEMPT_TYPE_VALUES = ", ".join(f"'{value}'" for value in ATTEMPT_TYPES)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    sessions: Mapped[list["TerminalSession"]] = relationship(back_populates="user")
    mission_attempts: Mapped[list["MissionAttempt"]] = relationship(back_populates="user")


class TerminalSession(Base):
    __tablename__ = "terminal_sessions"
    __table_args__ = (environment_check("terminal_sessions"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DEFAULT_ENVIRONMENT, server_default=DEFAULT_ENVIRONMENT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    command_logs: Mapped[list["CommandLog"]] = relationship(back_populates="session")


class CommandLog(Base):
    __tablename__ = "command_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("terminal_sessions.id"), nullable=False)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, default="")
    exit_code: Mapped[int] = mapped_column(Integer, default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    execution_time: Mapped[float] = mapped_column(Float, default=0.0)

    session: Mapped["TerminalSession"] = relationship(back_populates="command_logs")


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (
        environment_check("missions"),
        # 시드는 (environment, level) 을 stable key 로 upsert 한다.
        # 같은 환경에 같은 레벨이 두 개면 잠금 계산과 시드가 모두 깨진다.
        UniqueConstraint("environment", "level", name="uq_missions_environment_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    chaos_type: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DEFAULT_ENVIRONMENT, server_default=DEFAULT_ENVIRONMENT
    )
    base_score: Mapped[int] = mapped_column(Integer, default=100)
    time_limit: Mapped[int] = mapped_column(Integer, default=600)
    hint_penalty: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    attempts: Mapped[list["MissionAttempt"]] = relationship(back_populates="mission")


# GeneratedScenario를 MissionAttempt 앞에 선언 (FK 참조 순서)
class GeneratedScenario(Base):
    __tablename__ = "generated_scenarios"
    __table_args__ = (environment_check("generated_scenarios"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DEFAULT_ENVIRONMENT, server_default=DEFAULT_ENVIRONMENT
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    student_brief: Mapped[str] = mapped_column(Text, nullable=False)
    internal_summary: Mapped[str] = mapped_column(Text, nullable=False)
    fault_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scenario_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    chaos_plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # generated | running | completed | failed | rejected
    status: Mapped[str] = mapped_column(String(20), default="generated")
    safety_review: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chaos_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_score: Mapped[int] = mapped_column(Integer, default=100)
    time_limit: Mapped[int] = mapped_column(Integer, default=1200)
    hint_penalty: Mapped[int] = mapped_column(Integer, default=7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    attempts: Mapped[list["MissionAttempt"]] = relationship(back_populates="scenario")
    validation_rules: Mapped[list["ValidationRule"]] = relationship(back_populates="scenario")


class MissionAttempt(Base):
    __tablename__ = "mission_attempts"
    __table_args__ = (
        environment_check("mission_attempts"),
        CheckConstraint(
            f"attempt_type IN ({_ATTEMPT_TYPE_VALUES})",
            name="ck_mission_attempts_attempt_type",
        ),
        # attempt_type 과 실제 참조가 어긋난 행을 DB 단에서 막는다.
        CheckConstraint(
            "(attempt_type = 'static_mission'"
            " AND mission_id IS NOT NULL AND scenario_id IS NULL)"
            " OR (attempt_type = 'ai_scenario'"
            " AND scenario_id IS NOT NULL AND mission_id IS NULL)",
            name="ck_mission_attempts_type_refs",
        ),
        # 사용자당 진행 중 attempt 는 최대 1개. 기존 코드가 scalar_one_or_none() 을
        # 전제하고 있어 동시 요청 시 MultipleResultsFound 가 날 수 있었다.
        Index(
            "uq_mission_attempts_user_in_progress",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # static_mission: mission_id 필수, scenario_id null
    # ai_scenario: scenario_id 필수, mission_id null
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    attempt_type: Mapped[str] = mapped_column(String(20), default="static_mission")
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("generated_scenarios.id"), nullable=True)
    # 이 attempt 가 어느 훈련 환경에서 수행되는지. mission/scenario 를 join 하지 않고도
    # 정리·복구·통계를 할 수 있어야 한다.
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DEFAULT_ENVIRONMENT, server_default=DEFAULT_ENVIRONMENT
    )
    # 주입된 장애와 샌드박스 식별자. 서버가 재시작돼도 DB 만으로 정리할 수 있어야 한다.
    # (기존에는 프로세스 메모리 dict 에만 있었다)
    chaos_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sandbox_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    last_validation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="mission_attempts")
    mission: Mapped["Mission | None"] = relationship(back_populates="attempts")
    scenario: Mapped["GeneratedScenario | None"] = relationship(back_populates="attempts")


class ValidationRule(Base):
    __tablename__ = "validation_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("generated_scenarios.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)  # promql | k8s | mock
    query: Mapped[str] = mapped_column(Text, nullable=False)
    stability_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    guard_status: Mapped[str] = mapped_column(String(20), default="accepted")  # accepted | rejected
    guard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    scenario: Mapped["GeneratedScenario"] = relationship(back_populates="validation_rules")


class TutorMessage(Base):
    __tablename__ = "tutor_messages"
    # 보존 정책은 retention_service.purge_expired_tutor_messages 가 집행한다(BE-29).
    # created_at 에 인덱스를 두는 이유: 정리 작업이 기간 조건으로 훑는 컬럼이라
    # 인덱스가 없으면 대화가 쌓일수록 전체 스캔이 된다.
    __table_args__ = (Index("ix_tutor_messages_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mission_attempts.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    message: Mapped[str] = mapped_column(Text, nullable=False)
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
