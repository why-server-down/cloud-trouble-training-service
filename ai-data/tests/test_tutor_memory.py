import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.tutor_service import TutorService
from prompt_engine import SocraticPromptEngine, TrainingContext


def _message(role, text, hint=1):
    return SimpleNamespace(role=role, message=text, hint_level=hint)


def test_recent_five_user_assistant_pairs_are_kept_in_time_order():
    messages = []
    for index in range(7):
        messages.extend([
            _message("user", f"질문-{index}"),
            _message("assistant", f"답변-{index}"),
        ])
    history = TutorService._conversation_pairs(messages)
    assert len(history) == 5
    assert history[0]["user"] == "질문-2"
    assert history[-1]["assistant"] == "답변-6"


def test_incomplete_or_orphan_messages_are_not_mixed_into_pairs():
    messages = [
        _message("assistant", "고아 답변"),
        _message("user", "정상 질문"),
        _message("assistant", "정상 답변"),
        _message("user", "아직 답변 없음"),
    ]
    assert TutorService._conversation_pairs(messages) == [{
        "user": "정상 질문", "assistant": "정상 답변", "hint_level": 1,
    }]


def test_conversation_budget_prefers_recent_complete_pairs():
    messages = []
    for index in range(5):
        messages.extend([
            _message("user", f"질문-{index}-" + "가" * 300),
            _message("assistant", f"답변-{index}-" + "나" * 300),
        ])
    history = TutorService._conversation_pairs(messages, max_chars=1_000)
    assert len(history) == 1
    assert history[0]["user"].startswith("질문-4-")
    assert sum(len(pair["user"]) + len(pair["assistant"]) for pair in history) <= 1_000


@pytest.mark.asyncio
async def test_query_is_scoped_to_exact_attempt_and_reads_ten_messages():
    attempt_id = uuid.uuid4()

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _DB:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return _Result()

    db = _DB()
    assert await TutorService()._load_conversation(attempt_id, db) == []
    compiled = db.statement.compile()
    assert attempt_id in compiled.params.values()
    assert "tutor_messages.attempt_id" in str(db.statement)
    assert 10 in compiled.params.values()


def test_repeated_question_and_previous_answer_are_present_in_prompt():
    prompt = SocraticPromptEngine().generate_prompt(
        "Pod 상태를 다시 볼까요?",
        training_ctx=TrainingContext(
            user={"conversation_history": [{
                "user": "Pod 상태를 다시 볼까요?",
                "assistant": "이전에는 readiness를 살펴봤습니다.",
                "hint_level": 1,
            }]},
        ),
    )
    assert prompt.count("Pod 상태를 다시 볼까요?") == 2
    assert "이전에는 readiness를 살펴봤습니다." in prompt
