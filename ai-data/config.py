"""AI Tutor 설정.

standalone 실행은 ``AISettings.from_env()``를 사용하고, backend adapter는
``AISettings.from_backend_settings()``로 명시적인 설정 객체를 전달한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_GEMINI_EMBEDDING_MODEL = "models/gemini-embedding-001"


def _env_int(values: Mapping[str, str], name: str, default: int) -> int:
    return int(values.get(name, str(default)))


def _env_float(values: Mapping[str, str], name: str, default: float) -> float:
    return float(values.get(name, str(default)))


@dataclass(frozen=True)
class AISettings:
    """AI engine과 RAG가 공유하는 불변 설정."""

    AI_BACKEND: str = "mock"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = DEFAULT_OPENAI_MODEL
    TUTOR_MODEL: str = DEFAULT_OPENAI_MODEL
    EMBEDDING_MODEL: str = DEFAULT_OPENAI_EMBEDDING_MODEL
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: int = 500
    OPENAI_TIMEOUT: float = 10.0
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = DEFAULT_GEMINI_MODEL
    GEMINI_EMBEDDING_MODEL: str = DEFAULT_GEMINI_EMBEDDING_MODEL
    KNOWLEDGE_BASE_DIR: str = str(Path(__file__).resolve().parent / "knowledge-base")
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    RAG_TOP_K: int = 5
    RAG_MIN_SIMILARITY: float = 0.7
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200
    CONTEXT_COLLECTION_TIMEOUT: float = 3.0
    RAG_SEARCH_TIMEOUT: float = 2.0
    AI_MAX_CONTEXT_TOKENS: int = 9_000
    AI_MAX_COMPLETION_TOKENS: int = 500
    AI_MAX_RETRIEVED_CHUNKS: int = 5
    AI_PROVIDER_MAX_ATTEMPTS: int = 2

    def __post_init__(self) -> None:
        if self.AI_BACKEND not in {"mock", "openai", "gemini"}:
            raise ValueError(f"지원하지 않는 AI backend입니다: {self.AI_BACKEND}")
        if self.RAG_TOP_K < 0:
            raise ValueError("RAG_TOP_K는 0 이상이어야 합니다")
        if not 0 <= self.RAG_MIN_SIMILARITY <= 1:
            raise ValueError("RAG_MIN_SIMILARITY는 0과 1 사이여야 합니다")
        for name in (
            "AI_MAX_CONTEXT_TOKENS", "AI_MAX_COMPLETION_TOKENS",
            "AI_MAX_RETRIEVED_CHUNKS", "AI_PROVIDER_MAX_ATTEMPTS",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name}는 0보다 커야 합니다")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AISettings":
        values = os.environ if environ is None else environ
        openai_model = values.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        return cls(
            AI_BACKEND=values.get("AI_BACKEND", "mock"),
            OPENAI_API_KEY=values.get("OPENAI_API_KEY", ""),
            OPENAI_MODEL=openai_model,
            TUTOR_MODEL=values.get("TUTOR_MODEL", openai_model),
            EMBEDDING_MODEL=values.get("EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL),
            OPENAI_TEMPERATURE=_env_float(values, "OPENAI_TEMPERATURE", 0.7),
            OPENAI_MAX_TOKENS=_env_int(values, "OPENAI_MAX_TOKENS", 500),
            OPENAI_TIMEOUT=_env_float(values, "OPENAI_TIMEOUT", 10.0),
            GEMINI_API_KEY=values.get("GEMINI_API_KEY", ""),
            GEMINI_MODEL=values.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            GEMINI_EMBEDDING_MODEL=values.get(
                "GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL
            ),
            KNOWLEDGE_BASE_DIR=values.get(
                "KNOWLEDGE_BASE_DIR", str(Path(__file__).resolve().parent / "knowledge-base")
            ),
            QDRANT_URL=values.get("QDRANT_URL", "http://localhost:6333"),
            QDRANT_API_KEY=values.get("QDRANT_API_KEY", ""),
            RAG_TOP_K=_env_int(values, "RAG_TOP_K", 5),
            RAG_MIN_SIMILARITY=_env_float(values, "RAG_MIN_SIMILARITY", 0.7),
            RAG_CHUNK_SIZE=_env_int(values, "RAG_CHUNK_SIZE", 1000),
            RAG_CHUNK_OVERLAP=_env_int(values, "RAG_CHUNK_OVERLAP", 200),
            CONTEXT_COLLECTION_TIMEOUT=_env_float(values, "CONTEXT_COLLECTION_TIMEOUT", 3.0),
            RAG_SEARCH_TIMEOUT=_env_float(values, "RAG_SEARCH_TIMEOUT", 2.0),
            AI_MAX_CONTEXT_TOKENS=_env_int(values, "AI_MAX_CONTEXT_TOKENS", 9_000),
            AI_MAX_COMPLETION_TOKENS=_env_int(values, "AI_MAX_COMPLETION_TOKENS", 500),
            AI_MAX_RETRIEVED_CHUNKS=_env_int(values, "AI_MAX_RETRIEVED_CHUNKS", 5),
            AI_PROVIDER_MAX_ATTEMPTS=_env_int(values, "AI_PROVIDER_MAX_ATTEMPTS", 2),
        )

    @classmethod
    def from_backend_settings(cls, backend: object) -> "AISettings":
        """pydantic Settings를 환경변수 변경 없이 AI 설정으로 변환한다."""
        openai_model = getattr(backend, "OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        return cls(
            AI_BACKEND=getattr(backend, "AI_BACKEND", "mock"),
            OPENAI_API_KEY=getattr(backend, "OPENAI_API_KEY", ""),
            OPENAI_MODEL=openai_model,
            TUTOR_MODEL=getattr(backend, "TUTOR_MODEL", openai_model),
            EMBEDDING_MODEL=getattr(
                backend, "EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL
            ),
            OPENAI_TEMPERATURE=getattr(backend, "OPENAI_TEMPERATURE", 0.7),
            OPENAI_MAX_TOKENS=getattr(backend, "OPENAI_MAX_TOKENS", 500),
            OPENAI_TIMEOUT=getattr(backend, "OPENAI_TIMEOUT", 10.0),
            GEMINI_API_KEY=getattr(backend, "GEMINI_API_KEY", ""),
            GEMINI_MODEL=getattr(backend, "GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            GEMINI_EMBEDDING_MODEL=getattr(
                backend, "GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL
            ),
            KNOWLEDGE_BASE_DIR=getattr(
                backend,
                "KNOWLEDGE_BASE_DIR",
                str(Path(__file__).resolve().parent / "knowledge-base"),
            ),
            QDRANT_URL=getattr(backend, "QDRANT_URL", "http://localhost:6333"),
            QDRANT_API_KEY=getattr(backend, "QDRANT_API_KEY", ""),
            RAG_TOP_K=getattr(backend, "RAG_TOP_K", 5),
            RAG_MIN_SIMILARITY=getattr(backend, "RAG_MIN_SIMILARITY", 0.7),
            RAG_CHUNK_SIZE=getattr(backend, "RAG_CHUNK_SIZE", 1000),
            RAG_CHUNK_OVERLAP=getattr(backend, "RAG_CHUNK_OVERLAP", 200),
            CONTEXT_COLLECTION_TIMEOUT=getattr(backend, "CONTEXT_COLLECTION_TIMEOUT", 3.0),
            RAG_SEARCH_TIMEOUT=getattr(backend, "RAG_SEARCH_TIMEOUT", 2.0),
            AI_MAX_CONTEXT_TOKENS=getattr(backend, "AI_MAX_CONTEXT_TOKENS", 9_000),
            AI_MAX_COMPLETION_TOKENS=getattr(backend, "AI_MAX_COMPLETION_TOKENS", 500),
            AI_MAX_RETRIEVED_CHUNKS=getattr(backend, "AI_MAX_RETRIEVED_CHUNKS", 5),
            AI_PROVIDER_MAX_ATTEMPTS=getattr(backend, "AI_PROVIDER_MAX_ATTEMPTS", 2),
        )

    @property
    def provider_api_key(self) -> str:
        if self.AI_BACKEND == "gemini":
            return self.GEMINI_API_KEY
        if self.AI_BACKEND == "openai":
            return self.OPENAI_API_KEY
        return ""

    @property
    def tutor_model(self) -> str:
        return self.GEMINI_MODEL if self.AI_BACKEND == "gemini" else self.TUTOR_MODEL

    @property
    def embedding_model(self) -> str:
        return (
            self.GEMINI_EMBEDDING_MODEL
            if self.AI_BACKEND == "gemini"
            else self.EMBEDDING_MODEL
        )

    @property
    def api_base_url(self) -> str | None:
        if self.AI_BACKEND == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        return None

    def validate(self) -> bool:
        """secret 값을 출력하지 않고 현재 provider 설정 가능 여부만 반환한다."""
        if self.AI_BACKEND == "mock":
            return True
        return bool(self.provider_api_key and self.provider_api_key != "your_openai_api_key_here")

    def display(self) -> None:
        print(f"AI Backend: {self.AI_BACKEND}")
        print(f"Tutor Model: {self.tutor_model}")
        print(f"Embedding Model: {self.embedding_model}")
        print(f"Provider API Key: {'Set' if self.provider_api_key else 'Not Set'}")
        print(f"Qdrant URL: {self.QDRANT_URL}")
        print(f"RAG Top K: {self.RAG_TOP_K}")
        print(f"RAG Min Similarity: {self.RAG_MIN_SIMILARITY}")


# standalone 호환용 snapshot. backend production caller는 명시적 객체를 전달한다.
config = AISettings.from_env()

# 기존 import 호환. 새 코드는 AISettings를 사용한다.
Config = AISettings
