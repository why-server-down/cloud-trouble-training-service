# Knowledge Base

Kubernetes 트러블슈팅을 위한 지식 베이스 문서 모음

## 📁 구조

```
knowledge-base/
├── troubleshooting/          # 트러블슈팅 가이드
│   ├── crashloopbackoff.md   # CrashLoopBackOff 해결
│   ├── imagepullbackoff.md   # ImagePullBackOff 해결
│   ├── pending-pods.md        # Pending Pods 해결
│   └── oomkilled.md           # OOMKilled 해결
├── commands/                  # kubectl 명령어 가이드
│   └── kubectl-basics.md      # kubectl 기본 명령어
├── k8s_troubleshooting_guide.md  # 기존 가이드
├── survival_camp_playbook.md     # 기존 플레이북
└── README.md                  # 이 파일
```

## 📚 문서 목록

### 트러블슈팅 가이드

#### 1. CrashLoopBackOff (`troubleshooting/crashloopbackoff.md`)
Pod가 반복적으로 크래시하고 재시작하는 문제 해결

**주요 내용**:
- 원인: 애플리케이션 오류, 설정 문제, 리소스 문제, 의존성 문제
- 진단: Exit Code 확인, 로그 분석, Events 확인
- 해결: 로그 분석, 설정 확인, 리소스 조정, Probe 조정
- 실전 예제 4개

**키워드**: CrashLoopBackOff, Pod restart, Exit Code, 애플리케이션 크래시

---

#### 2. ImagePullBackOff (`troubleshooting/imagepullbackoff.md`)
컨테이너 이미지를 가져오는 데 실패하는 문제 해결

**주요 내용**:
- 원인: 이미지 이름 오류, 인증 문제, 네트워크 문제, 레지스트리 문제
- 진단: Events 확인, 이미지 정보 확인, imagePullSecrets 확인
- 해결: 이미지 이름 수정, Private 레지스트리 인증, Rate Limit 해결
- Docker Hub, AWS ECR, GCR, Harbor 인증 예제

**키워드**: ImagePullBackOff, ErrImagePull, imagePullSecrets, Private registry

---

#### 3. Pending Pods (`troubleshooting/pending-pods.md`)
Pod가 Pending 상태에 머물러 있는 문제 해결

**주요 내용**:
- 원인: 리소스 부족, Node Selector 불일치, Taints/Tolerations, PVC 문제
- 진단: Node 리소스 확인, 레이블 확인, Taint 확인
- 해결: 리소스 요청 조정, Node 추가, 레이블 관리, PVC 설정
- 실전 예제 4개

**키워드**: Pending, Insufficient resources, Node selector, Taints, PVC

---

#### 4. OOMKilled (`troubleshooting/oomkilled.md`)
메모리 부족으로 컨테이너가 종료되는 문제 해결

**주요 내용**:
- 원인: 메모리 제한 부족, 메모리 누수, 트래픽 급증, 비효율적인 코드
- 진단: Exit Code 137 확인, 메모리 사용량 확인, 메모리 프로파일링
- 해결: 메모리 제한 증가, 메모리 누수 수정, 코드 최적화, HPA/VPA
- Node.js, Python 메모리 프로파일링 예제

**키워드**: OOMKilled, Exit Code 137, Memory leak, Memory limit

---

### kubectl 명령어 가이드

#### 1. kubectl 기본 명령어 (`commands/kubectl-basics.md`)
kubectl의 가장 자주 사용되는 기본 명령어 모음

**주요 내용**:
- 클러스터 정보 및 Context 관리
- Pod 관리 (조회, 생성, 삭제)
- Deployment 관리 (생성, 업데이트, 스케일링, 롤백)
- Service 관리
- Namespace 관리
- ConfigMap & Secret 관리
- 레이블 및 어노테이션
- 유용한 팁 (출력 형식, 별칭, 자동 완성)

**키워드**: kubectl, get, describe, create, delete, logs, exec

---

## 🔍 문서 검색 가이드

### 증상별 문서 찾기

| 증상 | 문서 |
|------|------|
| Pod가 계속 재시작됨 | `crashloopbackoff.md` |
| 이미지를 가져올 수 없음 | `imagepullbackoff.md` |
| Pod가 시작되지 않음 (Pending) | `pending-pods.md` |
| 메모리 부족으로 종료됨 | `oomkilled.md` |
| kubectl 명령어를 모름 | `kubectl-basics.md` |

### Exit Code별 문서 찾기

| Exit Code | 의미 | 문서 |
|-----------|------|------|
| 0 | 정상 종료 | - |
| 1 | 일반 오류 | `crashloopbackoff.md` |
| 137 | OOMKilled | `oomkilled.md` |
| 139 | Segmentation Fault | `crashloopbackoff.md` |
| 143 | SIGTERM | `crashloopbackoff.md` |

### 키워드별 문서 찾기

- **CrashLoopBackOff**: `crashloopbackoff.md`
- **ImagePullBackOff**: `imagepullbackoff.md`
- **Pending**: `pending-pods.md`
- **OOMKilled**: `oomkilled.md`
- **kubectl**: `kubectl-basics.md`
- **리소스 부족**: `pending-pods.md`, `oomkilled.md`
- **인증**: `imagepullbackoff.md`
- **메모리**: `oomkilled.md`

---

## 📊 문서 통계

| 카테고리 | 문서 수 | 총 라인 수 | 평균 라인 수 |
|----------|---------|------------|--------------|
| 트러블슈팅 | 4 | ~1,200 | ~300 |
| kubectl 가이드 | 1 | ~400 | ~400 |
| **합계** | **5** | **~1,600** | **~320** |

---

## 🚀 사용 방법

### 1. 문서 직접 읽기

```bash
# 트러블슈팅 가이드
cat ai-data/knowledge-base/troubleshooting/crashloopbackoff.md

# kubectl 가이드
cat ai-data/knowledge-base/commands/kubectl-basics.md
```

### 2. RAG 시스템에 적재

```bash
# Knowledge Base를 Qdrant에 적재
cd ai-data
python scripts/ingest_knowledge.py
```

적재 후 AI 튜터가 이 문서들을 참조하여 답변합니다.

### 3. AI 튜터 사용

```bash
# AI 튜터 엔진 테스트
cd ai-data
python ai_engine.py
```

또는 Backend API를 통해:
```bash
# Backend 서버 실행
cd backend
uvicorn app.main:app --reload

# 챗봇 위젯 사용
open ../ai-chatbot-widget/demo-standalone.html
```

---

## ✍️ 문서 작성 가이드

새로운 문서를 추가하려면:

### 1. 파일 생성

```bash
# 트러블슈팅 가이드
touch ai-data/knowledge-base/troubleshooting/new-issue.md

# kubectl 가이드
touch ai-data/knowledge-base/commands/kubectl-advanced.md
```

### 2. 문서 구조

```markdown
# 제목

## 개요
문제에 대한 간단한 설명

## 증상
- 증상 1
- 증상 2

## 원인
### 1. 원인 1
설명

### 2. 원인 2
설명

## 진단 방법
### 1. 단계 1
```bash
명령어
```

## 해결 방법
### 1. 방법 1
설명 및 명령어

## 실전 예제
### 예제 1: 제목
**증상**:
**해결**:

## 예방 방법
### 1. 방법 1

## 체크리스트
- [ ] 항목 1
- [ ] 항목 2

## 디버깅 명령어 모음
```bash
명령어 모음
```

## 추가 리소스
- 링크 1
- 링크 2

## 요약
핵심 내용 요약
```

### 3. 문서 작성 팁

- **명확한 제목**: 문제를 명확히 표현
- **실전 예제**: 실제 상황 기반 예제 포함
- **명령어 포함**: 복사-붙여넣기 가능한 명령어
- **체크리스트**: 진단 시 확인할 사항
- **키워드**: 검색 가능한 키워드 포함
- **링크**: 공식 문서 링크 추가

### 4. RAG 시스템에 적재

```bash
# 새 문서 추가 후 재적재
cd ai-data
python scripts/ingest_knowledge.py
```

---

## 🔄 업데이트 로그

### 2026-06-01
- ✅ 트러블슈팅 가이드 4개 추가
  - CrashLoopBackOff
  - ImagePullBackOff
  - Pending Pods
  - OOMKilled
- ✅ kubectl 기본 명령어 가이드 추가
- ✅ Knowledge Base 적재 스크립트 작성

### 향후 계획
- [ ] kubectl 로그 조회 가이드
- [ ] kubectl describe 상세 가이드
- [ ] kubectl 디버깅 가이드
- [ ] Service 연결 문제 가이드
- [ ] Network 문제 가이드
- [ ] Storage 문제 가이드

---

## 📝 기여 가이드

새로운 문서를 추가하거나 기존 문서를 개선하려면:

1. 문서 작성 가이드를 따라 작성
2. 실전 예제 포함
3. 명령어 검증
4. RAG 시스템에 적재 테스트
5. AI 튜터 응답 품질 확인

---

## 📚 참고 자료

- [Kubernetes 공식 문서](https://kubernetes.io/docs/)
- [kubectl 치트 시트](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [Kubernetes 트러블슈팅](https://kubernetes.io/docs/tasks/debug/)

---

**작성일**: 2026-06-01  
**버전**: 1.0.0  
**문서 수**: 5개  
**총 라인 수**: ~1,600줄
