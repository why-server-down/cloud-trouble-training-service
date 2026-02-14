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
