"""외부 API와 Qdrant 서버 없이 AI 경로를 검증하는 결정적 fake."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Mapping, Sequence


class DeterministicFakeEmbeddings:
    """토큰 hashing을 사용해 실행마다 같은 정규화 벡터를 만든다."""

    def __init__(self, dimension: int = 64):
        if dimension <= 0:
            raise ValueError("dimension은 양수여야 합니다")
        self.dimension = dimension
        self.calls: list[str] = []

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_]+", text.casefold())

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        vector = [0.0] * self.dimension
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


@dataclass(frozen=True)
class FakeChatReply:
    content: str
    prompt_tokens: int = 12
    completion_tokens: int = 8


class DeterministicFakeChatCompletions:
    """입력에 포함된 키워드별로 고정 OpenAI 호환 응답을 반환한다."""

    def __init__(
        self,
        replies: Mapping[str, str | Mapping] | None = None,
        default: str = "어떤 상태를 먼저 관찰할 수 있을까요?",
    ):
        self.replies = dict(replies or {})
        self.default = default
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs.get("messages", [])
        text = "\n".join(str(message.get("content", "")) for message in messages)
        matched = next(
            (reply for keyword, reply in self.replies.items() if keyword in text),
            self.default,
        )
        content = (
            json.dumps(matched, ensure_ascii=False, sort_keys=True)
            if isinstance(matched, Mapping)
            else matched
        )
        reply = FakeChatReply(content=content)
        return SimpleNamespace(
            model=kwargs.get("model", "fake-model"),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=reply.content),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=reply.completion_tokens,
                total_tokens=reply.prompt_tokens + reply.completion_tokens,
            ),
        )


class DeterministicFakeOpenAI:
    def __init__(self, replies: Mapping[str, str | Mapping] | None = None):
        completions = DeterministicFakeChatCompletions(replies)
        self.chat = SimpleNamespace(completions=completions)
