"""명시적으로 선택할 때만 실행되는 실제 외부 서비스 smoke test."""

import os

import pytest


pytestmark = pytest.mark.integration


def test_openai_chat_completion():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY가 설정되지 않았습니다")

    from openai import OpenAI

    response = OpenAI(api_key=api_key).chat.completions.create(
        model=os.getenv("TUTOR_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": "Reply with: ok"}],
        max_tokens=3,
        temperature=0,
    )
    assert response.choices[0].message.content


def test_gemini_openai_compatible_completion():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY가 설정되지 않았습니다")

    from openai import OpenAI

    response = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ).chat.completions.create(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        messages=[{"role": "user", "content": "Reply with: ok"}],
        max_tokens=3,
        temperature=0,
    )
    assert response.choices[0].message.content


def test_external_qdrant_connection():
    qdrant_url = os.getenv("QDRANT_INTEGRATION_URL")
    if not qdrant_url:
        pytest.skip("QDRANT_INTEGRATION_URL이 설정되지 않았습니다")

    from qdrant_client import QdrantClient

    result = QdrantClient(
        url=qdrant_url,
        api_key=os.getenv("QDRANT_API_KEY") or None,
    ).get_collections()
    assert result.collections is not None
