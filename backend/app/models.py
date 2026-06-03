import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    chaos_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_score: Mapped[int] = mapped_column(Integer, default=100)
    time_limit: Mapped[int] = mapped_column(Integer, default=600)
    hint_penalty: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    attempts: Mapped[list["MissionAttempt"]] = relationship(back_populates="mission")


# GeneratedScenario를 MissionAttempt 앞에 선언 (FK 참조 순서)
class GeneratedScenario(Base):
    __tablename__ = "generated_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # static_mission: mission_id 필수, scenario_id null
    # ai_scenario: scenario_id 필수, mission_id null
    # NOTE: 기존 DB에서 mission_id NOT NULL 제약이 있다면 DROP 후 재생성 필요
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    attempt_type: Mapped[str] = mapped_column(String(20), default="static_mission")
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("generated_scenarios.id"), nullable=True)
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mission_attempts.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    message: Mapped[str] = mapped_column(Text, nullable=False)
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
