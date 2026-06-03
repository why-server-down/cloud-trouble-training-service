# ai-data - RAG 지식창고

K8s Survival Camp AI 튜터 및 시나리오 생성에 사용되는 RAG 엔진.

## 구조

```
ai-data/
├── knowledge-base/
│   ├── troubleshooting/    # K8s 장애 대응 문서
│   ├── commands/           # kubectl 명령어 레퍼런스
│   ├── incident-logs/      # 실제 클라우드 인시던트 로그 (추가 예정)
│   │   ├── eks/
│   │   ├── gke/
│   │   └── generic-k8s/
│   └── postmortems/        # 사후 분석 문서 (추가 예정)
├── prompts/
│   ├── socratic_tutor.md   # 소크라테스식 튜터 시스템 프롬프트
│   └── scenario_gen.md     # 시나리오 생성 프롬프트 (예정)
├── rag_service.py          # 벡터 검색 서비스 (Qdrant)
├── prompt_engine.py        # 프롬프트 조립 + 컨텍스트 삽입
├── ai_tutor_engine.py      # AI 튜터 엔진 (LangChain + OpenAI)
└── ingest.py               # 문서 → Qdrant 임베딩 스크립트
```

## 기술 스택

- **LangChain** - AI 파이프라인
- **OpenAI** - `text-embedding-3-small` (임베딩), `gpt-4o-mini` (생성)
- **Qdrant** - 벡터 DB (localhost:6333)

## RAG 검색

`RAGService.search_knowledge()`로 유사 문서 검색:

```python
results = rag_service.search_knowledge(
    query="OOMKilled memory limit",
    top_k=3,
    filters={"fault_type": "oom_killed", "difficulty": "intermediate"}
)
```

튜터 검색 쿼리는 사용자 질문만이 아닌 런타임 신호를 포함:

```
fault_type=oom_killed
symptoms=OOMKilled, restart_count=5, memory limit 6Mi
question=왜 Pod가 계속 재시작되나요?
```

## 인시던트 로그 문서 포맷

`knowledge-base/incident-logs/` 아래 마크다운 파일은 frontmatter 필수:

```markdown
---
title: EKS OOMKilled checkout-api incident
platform: eks
fault_type: oom_killed
difficulty: intermediate
signals:
  - OOMKilled
  - memory limit
  - restart_count
resolution:
  - memory limit increase
---

# 증상
...
# 진단 흐름
...
# 해결
...
```

## 문서 임베딩

```bash
cd ai-data
python ingest.py
```

Qdrant가 localhost:6333에서 실행 중이어야 함:

```bash
docker compose up qdrant -d
```

## 백엔드 연동

`backend/app/ai/tutor_service.py`가 `sys.path`로 이 모듈을 동적 import:

```python
# AI_BACKEND=mock: 고정 힌트 반환
# AI_BACKEND=openai: ai-data의 AITutorEngine + RAG + GPT
```
