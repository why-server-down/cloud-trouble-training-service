"""
Qdrant 자동 초기화 서비스.
서버 시작 시 컬렉션이 비어있으면 knowledge-base를 자동으로 ingestion한다.

조건:
- AI_BACKEND=mock → skip (임베딩 API 없음)
- Qdrant 컬렉션에 문서가 이미 있으면 → skip
- 위 두 조건 모두 아닐 때만 ingestion 실행
"""

import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

_AI_DATA_PATH_CANDIDATES = (
    os.getenv("AI_DATA_DIR"),
    os.path.abspath("/app/ai-data"),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../ai-data")),
)
_AI_DATA_PATH = next(
    (p for p in _AI_DATA_PATH_CANDIDATES if p and os.path.exists(p)),
    _AI_DATA_PATH_CANDIDATES[-1],
)


def _ensure_ai_data_path() -> bool:
    if not os.path.exists(_AI_DATA_PATH):
        logger.warning("ai-data directory not found at %s, skipping Qdrant auto-ingestion", _AI_DATA_PATH)
        return False
    if _AI_DATA_PATH not in sys.path:
        sys.path.insert(0, _AI_DATA_PATH)
    return True


def _run_ingestion() -> None:
    """blocking: Qdrant 컬렉션 확인 후 비어있으면 ingestion 실행."""
    from config import config  # ai-data/config.py
    from ingest import load_all_documents
    from rag_service import RAGService, RAGServiceError

    try:
        rag = RAGService()
    except RAGServiceError as e:
        logger.warning("Qdrant 연결 실패, auto-ingestion 건너뜀: %s", e)
        return

    try:
        stats = rag.get_collection_stats()
        if stats["document_count"] > 0:
            logger.info(
                "Qdrant 컬렉션에 문서 %d개 존재, ingestion 건너뜀",
                stats["document_count"],
            )
            return
    except RAGServiceError as e:
        logger.warning("Qdrant 컬렉션 조회 실패: %s", e)
        return

    logger.info("Qdrant 컬렉션이 비어있음, knowledge-base auto-ingestion 시작...")
    kb_dir = Path(config.KNOWLEDGE_BASE_DIR)
    if not kb_dir.exists():
        logger.warning("knowledge-base 디렉토리 없음: %s", kb_dir)
        return

    docs = load_all_documents(kb_dir)
    if not docs:
        logger.warning("knowledge-base에서 문서를 찾을 수 없음")
        return

    chunks = rag.chunk_documents(docs)
    count = rag.ingest_documents(chunks)
    logger.info("Auto-ingestion 완료: %d개 청크 적재", count)


async def auto_ingest_if_empty() -> None:
    """
    FastAPI lifespan에서 호출하는 비동기 진입점.
    임베딩 생성(CPU/네트워크 bound)은 ThreadPoolExecutor에서 실행한다.
    """
    # mock 모드는 임베딩 API 없으므로 경로 확인 전에 early return
    if os.getenv("AI_BACKEND", "mock") == "mock":
        logger.info("AI_BACKEND=mock, Qdrant auto-ingestion 건너뜀")
        return

    if not _ensure_ai_data_path():
        return

    try:
        from config import config  # ai-data/config.py
    except ImportError:
        logger.warning("ai-data config import 실패, auto-ingestion 건너뜀")
        return

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, _run_ingestion)
