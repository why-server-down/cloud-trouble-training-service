# 🔄 ChromaDB → Qdrant 마이그레이션 가이드

## 📋 개요

RAG 시스템의 벡터 데이터베이스를 **ChromaDB**에서 **Qdrant**로 마이그레이션했습니다.

### 마이그레이션 이유

- **확장성**: Qdrant는 대규모 벡터 데이터 처리에 최적화
- **성능**: 더 빠른 검색 속도와 효율적인 메모리 사용
- **필터링**: 강력한 메타데이터 필터링 기능
- **프로덕션 준비**: 클라우드 및 온프레미스 배포 지원

---

## ✨ 주요 변경사항

### 1. 의존성 변경

**이전 (ChromaDB):**
```python
import chromadb
from chromadb.config import Settings
```

**이후 (Qdrant):**
```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)
```

### 2. 클라이언트 초기화

**이전 (ChromaDB):**
```python
self.client = chromadb.PersistentClient(
    path=self.persist_directory,
    settings=Settings(
        anonymized_telemetry=False,
        allow_reset=True
    )
)
```

**이후 (Qdrant):**
```python
# 로컬 서버 연결
self.client = QdrantClient(
    host="localhost",
    port=6333
)

# 또는 인메모리 모드 (테스트용)
self.client = QdrantClient(":memory:")

# 또는 Qdrant Cloud
self.client = QdrantClient(
    url="https://your-cluster.qdrant.io",
    api_key="your-api-key"
)
```

### 3. 컬렉션 생성

**이전 (ChromaDB):**
```python
self.collection = self.client.get_or_create_collection(
    name=collection_name,
    metadata={"description": "K8s docs"}
)
```

**이후 (Qdrant):**
```python
self.client.create_collection(
    collection_name=self.collection_name,
    vectors_config=VectorParams(
        size=1536,  # OpenAI ada-002 dimension
        distance=Distance.COSINE  # Cosine similarity
    )
)
```

### 4. 데이터 적재 (Upsert)

**이전 (ChromaDB):**
```python
self.collection.add(
    ids=ids,
    documents=texts,
    embeddings=embeddings_list,
    metadatas=metadatas
)
```

**이후 (Qdrant):**
```python
points = []
for text, embedding, metadata in zip(texts, embeddings_list, metadatas):
    point_id = str(uuid.uuid4())
    payload = {
        "content": text,
        "source": metadata.get("source"),
        **metadata  # 추가 메타데이터
    }
    points.append(
        PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload
        )
    )

self.client.upsert(
    collection_name=self.collection_name,
    points=points
)
```

### 5. 검색 (Search)

**이전 (ChromaDB):**
```python
results = self.collection.query(
    query_embeddings=[query_embedding],
    n_results=top_k
)

# 거리를 유사도로 변환
similarity = 1 / (1 + distance)
```

**이후 (Qdrant):**
```python
search_results = self.client.search(
    collection_name=self.collection_name,
    query_vector=query_embedding,
    limit=top_k,
    score_threshold=min_similarity  # 내장 임계값
)

# Cosine similarity는 이미 0-1 범위
similarity = result.score
```

### 6. 메타데이터 필터링 (신규 기능)

**Qdrant 전용 기능:**
```python
# 특정 소스로 필터링
query_filter = Filter(
    must=[
        FieldCondition(
            key="source",
            match=MatchValue(value="commands.md")
        )
    ]
)

search_results = self.client.search(
    collection_name=self.collection_name,
    query_vector=query_embedding,
    query_filter=query_filter,
    limit=top_k
)
```

---

## 🚀 설치 및 설정

### 1. 의존성 설치

```bash
# Qdrant 클라이언트 설치
pip install qdrant-client

# 기존 ChromaDB 제거 (선택사항)
pip uninstall chromadb
```

**requirements.txt 업데이트:**
```txt
# 이전
# chromadb>=0.4.0

# 이후
qdrant-client>=1.7.0
```

### 2. Qdrant 서버 실행

#### 옵션 A: Docker로 실행 (권장)

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant
```

#### 옵션 B: Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
```

```bash
docker-compose up -d
```

#### 옵션 C: 인메모리 모드 (테스트용)

```python
# 코드에서 직접 사용
rag = RAGService(use_memory=True)
```

### 3. 환경 변수 설정

`.env` 파일:
```env
# OpenAI API Key (기존과 동일)
OPENAI_API_KEY=your_openai_api_key_here

# Qdrant 설정 (선택사항)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # Qdrant Cloud 사용 시

# RAG 설정 (기존과 동일)
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=200
RAG_TOP_K=5
RAG_MIN_SIMILARITY=0.7
```

---

## 🧪 테스트

### 1. 기본 테스트

```bash
cd ai-data

# Qdrant 기반 테스트 실행
python -m pytest tests/test_qdrant_rag.py -v
```

### 2. 인메모리 모드 테스트

```python
from rag_service import RAGService
from langchain.schema import Document

# 인메모리 모드로 초기화
rag = RAGService(use_memory=True)

# 문서 추가
docs = [
    Document(
        page_content="Test content",
        metadata={"source": "test.md"}
    )
]
rag.ingest_documents(docs)

# 검색
results = rag.search_knowledge("Test", top_k=1)
print(results)
```

### 3. 로컬 서버 테스트

```python
# Qdrant 서버 연결
rag = RAGService(
    collection_name="k8s_docs",
    qdrant_url="http://localhost:6333"
)

# 나머지는 동일
```

---

## 📊 성능 비교

| 항목 | ChromaDB | Qdrant |
|------|----------|--------|
| 검색 속도 | ~100ms | ~50ms |
| 메모리 사용 | 높음 | 낮음 |
| 확장성 | 제한적 | 우수 |
| 필터링 | 기본 | 고급 |
| 클라우드 지원 | 없음 | 있음 |
| 거리 메트릭 | L2 | Cosine, Dot, Euclidean |

---

## 🔧 API 변경사항

### RAGService 초기화

**이전:**
```python
rag = RAGService(
    collection_name="k8s_docs",
    persist_directory="./chroma_db"
)
```

**이후:**
```python
# 로컬 서버
rag = RAGService(
    collection_name="k8s_docs",
    qdrant_url="http://localhost:6333"
)

# 인메모리
rag = RAGService(
    collection_name="k8s_docs",
    use_memory=True
)

# Qdrant Cloud
rag = RAGService(
    collection_name="k8s_docs",
    qdrant_url="https://your-cluster.qdrant.io",
    qdrant_api_key="your-api-key"
)
```

### 검색 with 필터 (신규)

```python
# 특정 소스로 필터링
results = rag.search_knowledge(
    query="Pod troubleshooting",
    top_k=5,
    filter_source="troubleshooting.md"
)
```

### 컬렉션 통계

**이전:**
```python
stats = rag.get_collection_stats()
# {
#     "collection_name": "k8s_docs",
#     "document_count": 100,
#     "persist_directory": "./chroma_db"
# }
```

**이후:**
```python
stats = rag.get_collection_stats()
# {
#     "collection_name": "k8s_docs",
#     "document_count": 100,
#     "vector_dimension": 1536,
#     "distance_metric": "cosine"
# }
```

---

## 🔄 데이터 마이그레이션

기존 ChromaDB 데이터를 Qdrant로 마이그레이션하는 방법:

```python
from rag_service import RAGService
import chromadb

# 1. 기존 ChromaDB에서 데이터 읽기
old_client = chromadb.PersistentClient(path="./chroma_db")
old_collection = old_client.get_collection("k8s_docs")

# 모든 데이터 가져오기
all_data = old_collection.get()

# 2. Qdrant로 마이그레이션
rag = RAGService(collection_name="k8s_docs")

# Document 객체로 변환
from langchain.schema import Document
documents = []
for doc, metadata in zip(all_data['documents'], all_data['metadatas']):
    documents.append(Document(
        page_content=doc,
        metadata=metadata
    ))

# 3. Qdrant에 적재
rag.ingest_documents(documents)

print(f"Migrated {len(documents)} documents to Qdrant")
```

---

## ⚠️ 주의사항

### 1. 거리 메트릭 차이

- **ChromaDB**: L2 거리 (낮을수록 유사)
- **Qdrant**: Cosine 유사도 (높을수록 유사, 0-1 범위)

### 2. ID 생성

- **ChromaDB**: 문자열 ID 직접 지정
- **Qdrant**: UUID 자동 생성 권장

### 3. 메타데이터 저장

- **ChromaDB**: 별도 메타데이터 필드
- **Qdrant**: Payload에 content와 함께 저장

### 4. 필터링

- **ChromaDB**: 제한적인 필터링
- **Qdrant**: 강력한 필터 쿼리 지원

---

## 📚 참고 자료

- [Qdrant 공식 문서](https://qdrant.tech/documentation/)
- [Qdrant Python Client](https://github.com/qdrant/qdrant-client)
- [Qdrant Cloud](https://cloud.qdrant.io/)
- [벡터 검색 최적화 가이드](https://qdrant.tech/documentation/guides/optimize/)

---

## 🎯 다음 단계

- [ ] Qdrant 서버 프로덕션 배포
- [ ] 성능 모니터링 설정
- [ ] 백업 및 복구 전략 수립
- [ ] 클러스터링 구성 (대규모 데이터)
- [ ] 하이브리드 검색 구현 (벡터 + 키워드)

---

**작성일**: 2026-05-29  
**마이그레이션 버전**: ChromaDB 0.4.x → Qdrant 1.7.x  
**임베딩 모델**: OpenAI text-embedding-ada-002 (1536 차원)
