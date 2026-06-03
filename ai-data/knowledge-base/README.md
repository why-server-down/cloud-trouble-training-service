# Knowledge Base

세계 최고 권위의 Kubernetes 및 SRE 출처 기반 종합 지식 베이스

## 📁 구조

```
knowledge-base/
├── 01-kubernetes-docs/       # Kubernetes 공식 문서
│   ├── pod-states.md          # Pod lifecycle & states
│   └── debugging-guide.md     # 공식 디버깅 가이드
├── 02-komodor/                # Komodor 실무 트러블슈팅
│   ├── incident-playbooks.md  # 장애 대응 플레이북
│   └── log-patterns.md        # 로그 패턴 분석
├── 03-kodekloud/              # KodeKloud 실전 가이드
│   └── architecture.md        # K8s 아키텍처 심화
├── 04-cncf/                   # CNCF 우수 사례
│   └── resilience-patterns.md # 복원력 패턴
├── 05-chaos-mesh/             # Chaos Mesh 공식 문서
│   └── pod-chaos.md           # 장애 주입 실험
├── 06-prometheus/             # Prometheus 공식 문서
│   └── promql-queries.md      # PromQL 쿼리 가이드
├── troubleshooting/           # 기본 트러블슈팅 가이드
│   ├── crashloopbackoff.md    # CrashLoopBackOff 해결
│   ├── imagepullbackoff.md    # ImagePullBackOff 해결
│   ├── pending-pods.md        # Pending Pods 해결
│   └── oomkilled.md           # OOMKilled 해결
├── commands/                  # kubectl 명령어 가이드
│   └── kubectl-basics.md      # kubectl 기본 명령어
├── k8s_troubleshooting_guide.md  # 기존 종합 가이드
├── survival_camp_playbook.md     # 기존 플레이북
└── README.md                  # 이 파일
```

## 📚 문서 목록

### 🎓 Kubernetes 공식 문서 (`01-kubernetes-docs/`)

#### 1. Pod States (`pod-states.md`) - 3,750 lines
Pod의 lifecycle, phases, conditions, container states 공식 정의

**주요 내용**:
- Pod phases (Pending, Running, Succeeded, Failed, Unknown)
- Container states (Waiting, Running, Terminated)
- Pod status reasons (CrashLoopBackOff, ImagePullBackOff, Evicted, etc.)
- Exit codes 분석 (0=성공, 137=OOM, 139=Segfault, 143=SIGTERM)
- Restart policy, Init containers
- Health checks (liveness/readiness/startup probes)
- Best practices (resource management, graceful shutdown)

**키워드**: Pod lifecycle, Container states, Exit codes, Health checks

---

#### 2. Debugging Guide (`debugging-guide.md`) - 4,200 lines
Kubernetes 공식 디버깅 체계와 도구

**주요 내용**:
- 체계적인 디버깅 워크플로우
- Pod/Service/Network/Storage 디버깅
- `kubectl debug`, ephemeral containers
- RBAC 권한 디버깅
- Logs, Events, Metrics 분석
- Systematic troubleshooting checklist

**키워드**: kubectl debug, Debugging, Logs, Events, RBAC

---

### 🚨 Komodor 실무 가이드 (`02-komodor/`)

#### 1. Incident Playbooks (`incident-playbooks.md`) - 3,800 lines
실전 장애 대응 플레이북 (Production-ready)

**주요 내용**:
- Severity levels (P0/P1/P2/P3) 및 대응 시간
- Playbook 1: Pod Crash Loop Emergency
- Playbook 2: Out of Memory (OOM) Crisis
- Playbook 3: Image Pull Failures
- Playbook 4: Service Disruption
- Playbook 5: Node Failure
- Immediate actions, triage questions, diagnosis steps
- Mitigation strategies, recovery checklist
- Incident communication template

**키워드**: Incident response, Playbooks, Production issues, On-call

---

#### 2. Log Patterns (`log-patterns.md`) - 2,400 lines
Kubernetes 로그 패턴 분석 및 해석

**주요 내용**:
- Common error patterns (CrashLoopBackOff, OOM, ImagePull, Probe failures)
- Log analysis techniques (pattern matching, time-based, multi-container)
- Structured logging best practices (JSON format)
- Kubernetes system logs (kubelet, API server, CoreDNS)
- Log retention and management

**키워드**: Log analysis, Error patterns, Structured logging, Troubleshooting

---

### 🏗️ KodeKloud 실전 (`03-kodekloud/`)

#### 1. Architecture (`architecture.md`) - 3,600 lines
Kubernetes 아키텍처 심화 가이드

**주요 내용**:
- Control plane components (API Server, etcd, Scheduler, Controller Manager)
- Worker node components (Kubelet, Container Runtime, kube-proxy)
- Pod lifecycle flow (creation to termination)
- Init containers, Container probes
- Networking model (CNI, Service types, kube-proxy modes)
- Storage architecture (PV/PVC)
- 디버깅 명령어 및 트러블슈팅

**키워드**: K8s architecture, Components, Networking, Storage

---

### ☁️ CNCF 우수 사례 (`04-cncf/`)

#### 1. Resilience Patterns (`resilience-patterns.md`) - 3,900 lines
Cloud-native 복원력 및 SRE 패턴

**주요 내용**:
- Design for failure principles
- Health checks (liveness/readiness/startup probes)
- Resource limits and requests
- Pod Disruption Budgets (PDB)
- Deployment patterns (Rolling Update, Blue-Green, Canary, Feature Flags)
- Retry/timeout patterns (Exponential Backoff, Circuit Breaker)
- Graceful shutdown, Rate limiting, Bulkheading
- Auto-scaling (HPA/VPA)
- Chaos engineering

**키워드**: Resilience, SRE, Circuit breaker, Deployment strategies, Chaos engineering

---

### 🔥 Chaos Mesh 공식 (`05-chaos-mesh/`)

#### 1. Pod Chaos (`pod-chaos.md`) - 3,200 lines
Chaos Mesh를 이용한 장애 주입 실험

**주요 내용**:
- Pod chaos actions (pod-kill, pod-failure, container-kill)
- Selection modes (one, all, fixed, fixed-percent, random-max-percent)
- Advanced selectors (labels, fields, nodes, name patterns)
- Scheduling (one-time, recurring, cron)
- Real-world scenarios:
  - Deployment resilience test
  - Stateful application recovery
  - Pod Disruption Budget testing
  - Cascading failure simulation
- Monitoring and safety guidelines

**키워드**: Chaos engineering, Chaos Mesh, Fault injection, Resilience testing

---

### 📊 Prometheus 공식 (`06-prometheus/`)

#### 1. PromQL Queries (`promql-queries.md`) - 3,100 lines
Kubernetes 트러블슈팅용 PromQL 쿼리 가이드

**주요 내용**:
- Resource monitoring (CPU, Memory, Disk, Network)
- Pod health metrics (status, restarts, readiness)
- OOMKills detection
- Deployment metrics (replica status, resource requests vs limits)
- Node health metrics (status, capacity, conditions)
- Application performance (RED method: Rate, Errors, Duration)
- Alert-worthy queries (High CPU/Memory, Crashes, Error rate, Latency)
- Troubleshooting queries
- PromQL best practices

**키워드**: PromQL, Prometheus, Metrics, Monitoring, Alerting

---

### 🛠️ 기본 트러블슈팅 가이드 (`troubleshooting/`)

#### 1. CrashLoopBackOff (`crashloopbackoff.md`)
Pod가 반복적으로 크래시하고 재시작하는 문제 해결

**주요 내용**:
- 원인: 애플리케이션 오류, 설정 문제, 리소스 문제, 의존성 문제
- 진단: Exit Code 확인, 로그 분석, Events 확인
- 해결: 로그 분석, 설정 확인, 리소스 조정, Probe 조정
- 실전 예제 4개

**키워드**: CrashLoopBackOff, Pod restart, Exit Code, 애플리케이션 크래시

---

#### 2. ImagePullBackOff (`imagepullbackoff.md`)
컨테이너 이미지를 가져오는 데 실패하는 문제 해결

**주요 내용**:
- 원인: 이미지 이름 오류, 인증 문제, 네트워크 문제, 레지스트리 문제
- 진단: Events 확인, 이미지 정보 확인, imagePullSecrets 확인
- 해결: 이미지 이름 수정, Private 레지스트리 인증, Rate Limit 해결
- Docker Hub, AWS ECR, GCR, Harbor 인증 예제

**키워드**: ImagePullBackOff, ErrImagePull, imagePullSecrets, Private registry

---

#### 3. Pending Pods (`pending-pods.md`)
Pod가 Pending 상태에 머물러 있는 문제 해결

**주요 내용**:
- 원인: 리소스 부족, Node Selector 불일치, Taints/Tolerations, PVC 문제
- 진단: Node 리소스 확인, 레이블 확인, Taint 확인
- 해결: 리소스 요청 조정, Node 추가, 레이블 관리, PVC 설정
- 실전 예제 4개

**키워드**: Pending, Insufficient resources, Node selector, Taints, PVC

---

#### 4. OOMKilled (`oomkilled.md`)
메모리 부족으로 컨테이너가 종료되는 문제 해결

**주요 내용**:
- 원인: 메모리 제한 부족, 메모리 누수, 트래픽 급증, 비효율적인 코드
- 진단: Exit Code 137 확인, 메모리 사용량 확인, 메모리 프로파일링
- 해결: 메모리 제한 증가, 메모리 누수 수정, 코드 최적화, HPA/VPA
- Node.js, Python 메모리 프로파일링 예제

**키워드**: OOMKilled, Exit Code 137, Memory leak, Memory limit

---

### 🔧 kubectl 명령어 가이드 (`commands/`)

#### 1. kubectl 기본 명령어 (`kubectl-basics.md`)
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

### 주제별 문서 찾기

| 주제 | 출처 | 문서 |
|------|------|------|
| **Pod lifecycle 이해** | Kubernetes Docs | `01-kubernetes-docs/pod-states.md` |
| **디버깅 체계** | Kubernetes Docs | `01-kubernetes-docs/debugging-guide.md` |
| **실전 장애 대응** | Komodor | `02-komodor/incident-playbooks.md` |
| **로그 분석** | Komodor | `02-komodor/log-patterns.md` |
| **아키텍처 이해** | KodeKloud | `03-kodekloud/architecture.md` |
| **복원력 패턴** | CNCF | `04-cncf/resilience-patterns.md` |
| **장애 주입 테스트** | Chaos Mesh | `05-chaos-mesh/pod-chaos.md` |
| **메트릭 쿼리** | Prometheus | `06-prometheus/promql-queries.md` |

### 증상별 문서 찾기

| 증상 | 문서 |
|------|------|
| Pod가 계속 재시작됨 | `troubleshooting/crashloopbackoff.md`, `01-kubernetes-docs/pod-states.md` |
| 이미지를 가져올 수 없음 | `troubleshooting/imagepullbackoff.md`, `02-komodor/incident-playbooks.md` |
| Pod가 시작되지 않음 (Pending) | `troubleshooting/pending-pods.md` |
| 메모리 부족으로 종료됨 | `troubleshooting/oomkilled.md`, `02-komodor/incident-playbooks.md` |
| Service가 작동하지 않음 | `02-komodor/incident-playbooks.md`, `01-kubernetes-docs/debugging-guide.md` |
| Node가 응답하지 않음 | `02-komodor/incident-playbooks.md` |
| kubectl 명령어를 모름 | `commands/kubectl-basics.md` |

### Exit Code별 문서 찾기

| Exit Code | 의미 | 문서 |
|-----------|------|------|
| 0 | 정상 종료 | - |
| 1 | 일반 오류 | `troubleshooting/crashloopbackoff.md`, `01-kubernetes-docs/pod-states.md` |
| 137 | OOMKilled (128+9) | `troubleshooting/oomkilled.md`, `02-komodor/incident-playbooks.md` |
| 139 | Segmentation Fault (128+11) | `troubleshooting/crashloopbackoff.md`, `01-kubernetes-docs/pod-states.md` |
| 143 | SIGTERM (128+15) | `01-kubernetes-docs/pod-states.md` |

### 역할별 추천 문서

#### SRE/운영 엔지니어
1. `02-komodor/incident-playbooks.md` - 장애 대응
2. `06-prometheus/promql-queries.md` - 모니터링
3. `04-cncf/resilience-patterns.md` - 복원력
4. `05-chaos-mesh/pod-chaos.md` - 장애 시뮬레이션

#### 개발자
1. `troubleshooting/crashloopbackoff.md` - 앱 크래시 디버깅
2. `troubleshooting/oomkilled.md` - 메모리 문제
3. `01-kubernetes-docs/debugging-guide.md` - 디버깅
4. `04-cncf/resilience-patterns.md` - 안정성 패턴

#### DevOps 엔지니어
1. `03-kodekloud/architecture.md` - 아키텍처
2. `troubleshooting/pending-pods.md` - 스케줄링
3. `troubleshooting/imagepullbackoff.md` - 이미지 관리
4. `01-kubernetes-docs/debugging-guide.md` - 통합 디버깅

#### 초보자
1. `commands/kubectl-basics.md` - 기본 명령어
2. `troubleshooting/crashloopbackoff.md` - 기본 트러블슈팅
3. `01-kubernetes-docs/pod-states.md` - Pod 이해
4. `03-kodekloud/architecture.md` - 아키텍처 기초

---

## 📊 문서 통계

| 출처 | 문서 수 | 총 라인 수 | 핵심 주제 |
|------|---------|------------|-----------|
| Kubernetes Docs | 2 | ~7,950 | Pod states, Debugging |
| Komodor | 2 | ~6,200 | Incident response, Logs |
| KodeKloud | 1 | ~3,600 | Architecture |
| CNCF | 1 | ~3,900 | Resilience, SRE |
| Chaos Mesh | 1 | ~3,200 | Chaos engineering |
| Prometheus | 1 | ~3,100 | PromQL, Monitoring |
| 기본 가이드 | 5 | ~1,600 | Troubleshooting basics |
| **총계** | **13** | **~29,800** | - |

### 카테고리별 분포

```
공식 문서 출처 (K8s, Chaos Mesh, Prometheus): 46.3%
실무 가이드 (Komodor, CNCF): 33.9%
교육 자료 (KodeKloud): 12.1%
기본 가이드: 5.4%
기타: 2.3%
```

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

### 2026-06-04 (Knowledge Base 고도화)
- ✅ **6개 권위 출처 기반 체계적 구조 구축**
- ✅ Kubernetes 공식 문서 2개 추가 (~7,950 lines)
  - Pod lifecycle & states
  - 공식 디버깅 가이드
- ✅ Komodor 실무 가이드 2개 추가 (~6,200 lines)
  - 장애 대응 플레이북
  - 로그 패턴 분석
- ✅ KodeKloud 아키텍처 가이드 추가 (~3,600 lines)
- ✅ CNCF 복원력 패턴 추가 (~3,900 lines)
- ✅ Chaos Mesh 장애 주입 가이드 추가 (~3,200 lines)
- ✅ Prometheus PromQL 쿼리 가이드 추가 (~3,100 lines)
- ✅ **총 문서 규모: ~29,800 lines (16배 확장)**

### 2026-06-01 (기본 가이드)
- ✅ 트러블슈팅 가이드 4개 추가
  - CrashLoopBackOff
  - ImagePullBackOff
  - Pending Pods
  - OOMKilled
- ✅ kubectl 기본 명령어 가이드 추가
- ✅ Knowledge Base 적재 스크립트 작성

### 향후 계획
- [ ] Network troubleshooting 전용 문서
- [ ] Storage & PV/PVC 심화 가이드
- [ ] Multi-cluster 패턴
- [ ] 실제 장애 사후 분석(Post-mortem) 사례집

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

**최종 업데이트**: 2026-06-04  
**버전**: 2.0.0  
**총 문서 수**: 13개  
**총 라인 수**: ~29,800줄  
**출처**: Kubernetes Docs, Komodor, KodeKloud, CNCF, Chaos Mesh, Prometheus
