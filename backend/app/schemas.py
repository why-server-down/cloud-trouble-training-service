import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# Auth
class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime
    missions_completed: int
    total_score: int

    class Config:
        from_attributes = True


# Terminal
class SessionCreate(BaseModel):
    pass


class SessionResponse(BaseModel):
    id: uuid.UUID
    namespace: str
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


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


# Mission
class MissionResponse(BaseModel):
    id: uuid.UUID
    name: str
    level: int
    description: str
    chaos_type: str
    base_score: int
    time_limit: int
    hint_penalty: int
    is_unlocked: bool = False

    class Config:
        from_attributes = True


class MissionAttemptCreate(BaseModel):
    mission_id: uuid.UUID


class MissionAttemptResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    mission_id: Optional[uuid.UUID] = None
    attempt_type: str = "static_mission"
    scenario_id: Optional[uuid.UUID] = None
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    final_score: Optional[int] = None
    hints_used: int

    class Config:
        from_attributes = True


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


# AI Scenario
class ScenarioGenerateRequest(BaseModel):
    difficulty: str  # beginner | intermediate | advanced | expert
    randomize: bool = True


class ScenarioResponse(BaseModel):
    scenario_id: uuid.UUID
    title: str
    difficulty: str
    student_brief: str
    time_limit_seconds: int
    base_score: int
    hint_penalty: int
    safety_status: str = "accepted"

    class Config:
        from_attributes = True


class ScenarioStatusResponse(BaseModel):
    scenario_id: uuid.UUID
    attempt_id: uuid.UUID
    title: str
    difficulty: str
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


class UnlockStatusResponse(BaseModel):
    unlocked: bool
    completed_static: int
    total_static: int
