# 배포 매니페스트 (BE-25)

로컬 Docker Desktop Kubernetes 와 EKS 양쪽에 같은 것을 적용한다. 클라우드 고유
리소스(Ingress, 스토리지 클래스, 관리형 DB)는 여기 두지 않고 배포 시점에 얹는다.

```bash
kubectl apply -f base/admission-policy.yaml     # RBAC 으로 못 좁히는 부분을 막는다
kubectl apply -k base/
kubectl -n afterfail create secret generic afterfail-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=DATABASE_URL='postgresql+asyncpg://USER:PASS@HOST:5432/afterfail' \
  --from-literal=GEMINI_API_KEY='...'
kubectl apply -f base/migration-job.yaml         # 스키마를 먼저 맞춘다
kubectl -n afterfail wait --for=condition=complete job/afterfail-migrate --timeout=5m
```

## 왜 이렇게 나눴나

### 배포 경계 — privileged 는 클라우드에 올리지 않는다

| 환경 | 배포 | 근거 |
|---|---|---|
| Kubernetes | 클라우드 | 샌드박스가 비특권이다 |
| Linux | 클라우드 | BE-17 에서 hostPID/hostNetwork/SA 토큰 없이 설계했다 |
| **Docker(DinD)** | **로컬 데모 한정** | privileged 가 필요하다 |

privileged 컨테이너는 사실상 노드와 같은 권한이다. 탈출에 성공하면 노드를 잡고,
클라우드에서는 거기서 인스턴스 메타데이터(IMDS)로 노드 IAM 역할의 자격증명까지
닿는다. 훈련 샌드박스는 **사용자가 임의 명령을 치는 곳**이므로 그 경로를 열지 않는다.

명령 정책(`command_validator`)이 좁혀 두긴 하지만 그건 애플리케이션 계층 방어이고,
privileged 자체를 막지 못한다.

별도 node group + taint 로 격리하는 선택지도 있으나, Docker 환경 미션 3개를 위해
전용 노드를 상시 띄우는 비용이 이득보다 크다고 판단했다.

### Secret 은 저장소에 두지 않는다

커밋된 값은 지워도 히스토리에 남는다. `secret.template.yaml` 은 **키 목록일 뿐**이고
kustomization 에서 의도적으로 빠져 있다(적용하면 실제 Secret 을 placeholder 로 덮는다).

### 마이그레이션은 배포 전 Job 으로

앱은 `AUTO_CREATE_SCHEMA=false` 로 돈다. Job 보다 백엔드가 먼저 뜨면 기동 시
스키마 드리프트 검사에 걸려 CrashLoopBackOff 로 기다린다. **이건 설계된 동작이다** —
옛 스키마 위에서 조용히 도는 것보다 뜨지 않는 편이 낫다. Job 이 끝나면 다음
재시도에서 정상 기동한다. Job 과 Deployment 는 **같은 이미지 태그**를 써야 한다.

### 백엔드 권한 — ClusterRole 이 필요한 이유와 그 구멍

백엔드는 사용자 네임스페이스를 실행 시점에 만든다(`user-{uuid}`). RBAC 은
네임스페이스 이름을 패턴으로 표현할 수 없고 `resourceNames` 는 `create` 에 쓸 수 없다.
그래서 ClusterRole 을 쓸 수밖에 없는데, **ClusterRole 은 모든 네임스페이스에 적용된다.**

실측(2026-09-02)으로 확인한 구멍:

```
create pods -n kube-system              → yes   ← 열려 있었다
create deployments.apps -n kube-system  → yes   ← 열려 있었다
```

`kube-system` 에는 보통 PSA 강제가 없어 특권 Pod 를 만들 수 있고, 그러면 노드를 잡는
경로가 된다. `admission-policy.yaml`(ValidatingAdmissionPolicy)이 백엔드
ServiceAccount 의 요청을 `user-*` 와 `chaos-mesh` 로 제한해 이것을 닫는다.

> Kubernetes **1.30+** 기능이다. 더 낮은 클러스터라면 같은 규칙을 Kyverno 나 OPA
> Gatekeeper 로 옮겨야 한다. **이 정책이 없으면 위 권한이 그대로 열려 있다.**

## 실측 결과 (2026-09-02, Docker Desktop Kubernetes v1.34.3)

### RBAC

| 확인 | 결과 |
|---|---|
| `create namespaces` | yes |
| `create pods/exec -n user-x` | yes |
| `create stresschaos -n chaos-mesh` | yes |
| `get secrets -n kube-system` | **no** |
| `create clusterroles` | **no** |
| `delete nodes` | **no** |
| `escalate roles -n user-x` | **no** |
| `bind clusterroles` | **no** |
| `create podchaos -n chaos-mesh` | **no** (코드가 쓰는 것은 stresschaos 뿐) |
| `create stresschaos -n user-x` | **no** |

### Admission 정책

| 요청 | 결과 |
|---|---|
| `kube-system` 에 Pod 생성 | **Forbidden** |
| `default` 에 Deployment 생성 | **Forbidden** |
| `user-*` 에 Pod 생성 | 통과 |

### Pod Security Admission

`afterfail` 네임스페이스는 `restricted` 를 **강제**한다(warn/audit 이 아니다).

- securityContext 없는 Pod → `violates PodSecurity "restricted:latest"` 로 거절
- 백엔드 Deployment·마이그레이션 Job → 서버 dry-run 통과

### ResourceQuota

limits/requests 를 지정하지 않은 Pod 는 `failed quota: afterfail-quota` 로 거절된다.

## 아직 안 한 것

- **실제 EKS 배포는 하지 않았다.** 위 검증은 전부 로컬 클러스터에서 했다.
  EKS 에서 추가로 확인해야 하는 것: NetworkPolicy 를 강제할 CNI(기본 VPC CNI 는
  NetworkPolicy 를 강제하려면 활성화가 필요하다), API 서버 엔드포인트 대역에 맞춘
  egress 규칙, IRSA, IMDSv2 hop limit.
- Ingress, TLS, 관리형 DB(RDS) 매니페스트.
- 프론트엔드 매니페스트(프론트 담당 소유).
