import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.core.environments import DEFAULT_ENVIRONMENT, EnvironmentId


# Auth
class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime
    missions_completed: int
    total_score: int

    model_config = ConfigDict(from_attributes=True)


# Terminal
class SessionCreate(BaseModel):
    environment: EnvironmentId = DEFAULT_ENVIRONMENT


class SessionResponse(BaseModel):
    id: uuid.UUID
    namespace: str
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    created_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# WebSocket Messages
class CommandMessage(BaseModel):
    type: str = "command"
    command: str


class OutputMessage(BaseModel):
    type: str = "output"
    data: str
    exit_code: int = 0
    execution_time: float = 0.0


class ErrorMessage(BaseModel):
    type: str = "error"
    message: str
    code: str = "UNKNOWN"


# Environments
class EnvironmentItem(BaseModel):
    id: EnvironmentId
    status: str  # available | preparing
    capabilities: list[str] = []


class EnvironmentListResponse(BaseModel):
    items: list[EnvironmentItem]


# Mission
class MissionResponse(BaseModel):
    id: uuid.UUID
    name: str
    level: int
    description: str
    chaos_type: str
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    base_score: int
    time_limit: int
    hint_penalty: int
    is_unlocked: bool = False

    model_config = ConfigDict(from_attributes=True)


class MissionAttemptCreate(BaseModel):
    mission_id: uuid.UUID


class MissionAttemptResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    mission_id: Optional[uuid.UUID] = None
    attempt_type: str = "static_mission"
    scenario_id: Optional[uuid.UUID] = None
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    final_score: Optional[int] = None
    hints_used: int

    model_config = ConfigDict(from_attributes=True)


class MissionStatusResponse(BaseModel):
    attempt: MissionAttemptResponse
    elapsed_seconds: int
    remaining_seconds: int
    current_score: int


class MissionCompleteResponse(BaseModel):
    attempt: MissionAttemptResponse
    message: str


# AI Chat
class ChatRequest(BaseModel):
    message: str
    hint_level: int = 0  # 0~3 (소크라테스식 힌트 레벨)


class ChatResponse(BaseModel):
    response: str
    hint_level: int
    mission_name: Optional[str] = None
    sources: Optional[list[dict]] = None
    observations_used: Optional[list[str]] = None
    token_usage: Optional[dict] = None
    fallback_used: bool = False


# AI Scenario
class ScenarioGenerateRequest(BaseModel):
    difficulty: str  # beginner | intermediate | advanced | expert
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    randomize: bool = True
    demo_unlock: bool = False


class ScenarioResponse(BaseModel):
    scenario_id: uuid.UUID
    title: str
    difficulty: str
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    student_brief: str
    time_limit_seconds: int
    base_score: int
    hint_penalty: int
    safety_status: str = "accepted"

    model_config = ConfigDict(from_attributes=True)


class ScenarioStatusResponse(BaseModel):
    scenario_id: uuid.UUID
    attempt_id: uuid.UUID
    title: str
    difficulty: str
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    student_brief: str
    elapsed_seconds: int
    remaining_seconds: int
    current_score: int
    hints_used: int
    status: str


class ScenarioCheckResponse(BaseModel):
    resolved: bool
    message: str
    score: Optional[int] = None


# AI 계층 실행 계약 (BE-20)
# AI 담당이 이 형태로 결과를 돌려주면 백엔드가 저장·표시한다.
class TutorSource(BaseModel):
    """튜터 답변의 근거. 표시 가능한 필드만 담는다."""

    title: str
    source_id: Optional[str] = None
    # 외부 링크를 그대로 렌더링하지 않는다. 안전한 경로만 프론트가 anchor 로 만든다.
    path: Optional[str] = None
    environment: Optional[EnvironmentId] = None
    similarity: Optional[float] = None


class TutorResult(BaseModel):
    """AI 튜터 응답 계약."""

    message: str
    hint_level: int = 0
    environment: EnvironmentId = DEFAULT_ENVIRONMENT
    sources: list[TutorSource] = []
    # 답변에 실제로 쓰인 관측값의 이름. 정답이 아니라 무엇을 봤는지를 알린다.
    observations_used: list[str] = []
    # 운영 지표. 사용량과 지연을 추적한다(BE-23 메트릭과 연결된다).
    token_usage: Optional[dict] = None
    latency_ms: Optional[int] = None
    # 프로바이더 실패로 대체 응답을 준 경우
    fallback_used: bool = False
    error_code: Optional[str] = None


class ValidationJudgment(BaseModel):
    """LLM 검증 판정. **advisory 전용이다.**

    점수를 승인하는 유일한 기준은 mechanical validation 이다. 이 판정은 설명을
    돕기 위해 저장될 뿐, mechanical false 를 true 로 뒤집지 못한다.
    LLM 이 오판하면 사용자가 고치지 않았는데도 완료 처리되기 때문이다.
    """

    resolved: bool
    reason: str
    confidence: float = 0.0
    advisory_only: bool = True


class UnlockStatusResponse(BaseModel):
    unlocked: bool
    completed_static: int
    total_static: int
