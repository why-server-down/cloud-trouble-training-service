"""AI-01 explicit settings matrix tests (network/API key 불필요)."""

import os
import ast
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import (  # noqa: E402
    AISettings,
    DEFAULT_GEMINI_EMBEDDING_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    DEFAULT_OPENAI_MODEL,
)


def test_mock_defaults_are_offline_and_deterministic():
    settings = AISettings.from_env({})

    assert settings.AI_BACKEND == "mock"
    assert settings.validate() is True
    assert settings.TUTOR_MODEL == DEFAULT_OPENAI_MODEL
    assert settings.EMBEDDING_MODEL == DEFAULT_OPENAI_EMBEDDING_MODEL


def test_openai_matrix_uses_explicit_values():
    settings = AISettings.from_env({
        "AI_BACKEND": "openai",
        "OPENAI_API_KEY": "test-openai-key",
        "TUTOR_MODEL": "openai-tutor-test",
        "EMBEDDING_MODEL": "openai-embedding-test",
        "OPENAI_TIMEOUT": "4.5",
        "RAG_TOP_K": "0",
        "RAG_MIN_SIMILARITY": "0",
    })

    assert settings.validate() is True
    assert settings.tutor_model == "openai-tutor-test"
    assert settings.embedding_model == "openai-embedding-test"
    assert settings.OPENAI_TIMEOUT == 4.5
    assert settings.RAG_TOP_K == 0
    assert settings.RAG_MIN_SIMILARITY == 0


def test_gemini_matrix_uses_compatible_endpoint():
    settings = AISettings.from_env({
        "AI_BACKEND": "gemini",
        "GEMINI_API_KEY": "test-gemini-key",
    })

    assert settings.validate() is True
    assert settings.tutor_model == DEFAULT_GEMINI_MODEL
    assert settings.embedding_model == DEFAULT_GEMINI_EMBEDDING_MODEL
    assert settings.api_base_url.endswith("/v1beta/openai/")


def test_backend_adapter_does_not_mutate_environment():
    before = dict(os.environ)
    backend = SimpleNamespace(
        AI_BACKEND="openai",
        OPENAI_API_KEY="backend-key",
        OPENAI_MODEL=DEFAULT_OPENAI_MODEL,
        TUTOR_MODEL="backend-tutor",
        EMBEDDING_MODEL=DEFAULT_OPENAI_EMBEDDING_MODEL,
    )

    settings = AISettings.from_backend_settings(backend)

    assert settings.tutor_model == "backend-tutor"
    assert dict(os.environ) == before


def test_backend_and_standalone_defaults_match():
    standalone = AISettings.from_env({})
    backend = AISettings.from_backend_settings(SimpleNamespace())

    assert backend.OPENAI_MODEL == standalone.OPENAI_MODEL
    assert backend.TUTOR_MODEL == standalone.TUTOR_MODEL
    assert backend.EMBEDDING_MODEL == standalone.EMBEDDING_MODEL
    assert backend.GEMINI_MODEL == standalone.GEMINI_MODEL
    assert backend.GEMINI_EMBEDDING_MODEL == standalone.GEMINI_EMBEDDING_MODEL
    assert backend.RAG_TOP_K == standalone.RAG_TOP_K
    assert backend.RAG_MIN_SIMILARITY == standalone.RAG_MIN_SIMILARITY


def test_backend_declared_provider_defaults_match():
    backend_config = Path(__file__).resolve().parents[2] / "backend/app/core/config.py"
    tree = ast.parse(backend_config.read_text(encoding="utf-8"))
    settings_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    defaults = {
        node.target.id: ast.literal_eval(node.value)
        for node in settings_class.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
        and node.target.id in {
            "OPENAI_MODEL",
            "TUTOR_MODEL",
            "EMBEDDING_MODEL",
            "GEMINI_MODEL",
            "GEMINI_EMBEDDING_MODEL",
        }
    }
    standalone = AISettings.from_env({})

    assert defaults["OPENAI_MODEL"] == standalone.OPENAI_MODEL
    assert defaults["TUTOR_MODEL"] == standalone.TUTOR_MODEL
    assert defaults["EMBEDDING_MODEL"] == standalone.EMBEDDING_MODEL
    assert defaults["GEMINI_MODEL"] == standalone.GEMINI_MODEL
    assert defaults["GEMINI_EMBEDDING_MODEL"] == standalone.GEMINI_EMBEDDING_MODEL


def test_invalid_backend_is_rejected_without_exposing_key():
    try:
        AISettings(AI_BACKEND="invalid", OPENAI_API_KEY="must-not-appear")
    except ValueError as exc:
        assert "must-not-appear" not in str(exc)
    else:
        raise AssertionError("invalid backend must fail")
