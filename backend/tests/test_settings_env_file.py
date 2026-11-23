"""backend 설정은 실행 위치와 상관없이 backend/.env 만 읽는다.

저장소 루트의 .env 는 docker compose 전용이다(GF_SECURITY_ADMIN_PASSWORD 등). 예전에는
env_file=".env" 가 실행 위치 기준이라, 루트에서 ai-data 테스트를 돌리면 그 파일을 읽고
모르는 키(extra_forbidden)로 실패했다.
"""
from pathlib import Path

from app.core.config import BACKEND_ENV_FILE, Settings


def test_env_file_is_backend_dotenv():
    assert BACKEND_ENV_FILE == Path(__file__).resolve().parents[1] / ".env"


def test_stray_dotenv_in_working_directory_is_ignored(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GF_SECURITY_ADMIN_PASSWORD=admin\nSECRET_KEY=from-root\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    settings = Settings()

    assert settings.SECRET_KEY != "from-root"
