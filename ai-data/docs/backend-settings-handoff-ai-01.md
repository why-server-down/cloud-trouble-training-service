# AI-01 백엔드 설정 인계

AI 설정 객체는 누락된 backend 필드에 대해 아래 기본값을 사용한다. 설정의 단일 주입 경로를 완성하려면 백엔드 담당이 `backend/app/core/config.py`와 환경변수 문서에 같은 키를 추가해야 한다.

| 키 | 기본값 | 용도 |
|---|---:|---|
| `OPENAI_TEMPERATURE` | `0.7` | 튜터 응답 temperature |
| `OPENAI_MAX_TOKENS` | `500` | 튜터 completion 상한 |
| `OPENAI_TIMEOUT` | `10.0` | LLM 요청 timeout(초) |
| `RAG_TOP_K` | `5` | 기본 검색 결과 수 |
| `RAG_MIN_SIMILARITY` | `0.7` | 검색 score threshold |
| `RAG_CHUNK_SIZE` | `1000` | ingestion chunk 크기 |
| `RAG_CHUNK_OVERLAP` | `200` | ingestion chunk overlap |
| `CONTEXT_COLLECTION_TIMEOUT` | `3.0` | runtime context timeout(초) |
| `RAG_SEARCH_TIMEOUT` | `2.0` | RAG 검색 timeout(초) |

현재 backend에 이미 존재하며 standalone 기본값과 일치시킨 키:

- `OPENAI_MODEL=gpt-4o-mini`
- `TUTOR_MODEL=gpt-4o-mini`
- `EMBEDDING_MODEL=text-embedding-3-small`
- `GEMINI_MODEL=gemini-2.5-flash-lite`
- `GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001`

추가 backend 후속 작업:

- `backend/app/services/qdrant_init.py`에서도 환경변수 snapshot 대신 backend Settings로 만든 `AISettings`를 `RAGService`에 전달한다.
- `backend/requirements.txt` 변경은 필요 없다. 이미 Qdrant production dependency를 포함한다.
