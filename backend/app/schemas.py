import uuid
from datetime import datetime

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
    mission_id: uuid.UUID
    status: str
    start_time: datetime
    end_time: datetime | None
    final_score: int | None
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
    mission_name: str | None = None
