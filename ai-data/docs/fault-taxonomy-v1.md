# AfterFail AI 환경·장애 분류 v1

> 버전: `v1`
> 확정일: 2026-08-27
> 적용 범위: Kubernetes, Docker, Linux
> 제외 범위: Application, Database

## 1. 계약 원칙

- environment 값은 `kubernetes`, `docker`, `linux`만 사용한다.
- AI가 생성할 수 있는 fault는 backend compiler, injector, mechanical validator가 모두 준비된 항목으로 제한한다.
- 이 문서는 AI knowledge/eval에서 사용할 taxonomy snapshot이다. 실행 허용 여부의 최종 기준은 backend allowlist와 API 계약이다.
- backend 구현 전 fault는 문서·평가 준비용 후보로만 관리하며 scenario 생성 allowed list에 전달하지 않는다.
- LLM 판단은 복구 설명을 보조할 수 있지만 완료와 점수는 mechanical validator만 확정한다.
- Application/DB는 `v1`에서 environment 및 fault taxonomy에 포함하지 않는다.

## 2. 현재 생성 허용 범위

| environment | 생성 허용 | 상태 | backend 근거 |
|---|---|---|---|
| `kubernetes` | 아래 canonical 15종 | 활성 | `ChaosPlanCompiler`, `ChaosMeshInjector`, `ValidationRuleService` 구현 |
| `docker` | 없음 | 비활성 | BE-13 injector와 BE-14 validator 완료 후 활성화 |
| `linux` | 없음 | 비활성 | BE-17 injector와 BE-18 validator 완료 후 활성화 |

Docker/Linux 요청에서 allowed list가 비어 있으면 명시적 미지원 오류를 반환해야 한다. Kubernetes fixture나 fault로 fallback하지 않는다.

## 3. Kubernetes canonical taxonomy

| fault type | learning objective | observable signals | allowed recovery action | mechanical validator | backend 연결 |
|---|---|---|---|---|---|
| `image_pull_error` | 이미지 태그와 pull event 진단 | ImagePullBackOff, ErrImagePull, image event | Deployment image를 허용된 정상 이미지로 변경 | `deployment:nginx:running` | compiler → `pod_failure` injector → K8s rule |
| `crash_loop` | 종료 코드와 반복 재시작 원인 진단 | CrashLoopBackOff, exit code 1, restart 증가 | 잘못된 container command 제거/수정 | `deployment:nginx:running` | compiler → `crash_loop` injector → K8s rule |
| `oom_killed` | memory limit과 OOMKilled 연관 분석 | OOMKilled, exit 137, restart 증가 | namespace 제한 안에서 memory request/limit 정상화 | `deployment:nginx:running` | compiler → `memory_stress` injector → K8s rule |
| `probe_failure` | readiness와 traffic routing 관계 이해 | Running, Ready 0/1, endpoint 제외 | 잘못된 readiness probe 제거/수정 | `deployment:nginx:running` | compiler → `network_latency` injector → K8s rule |
| `liveness_probe_failure` | liveness 실패와 재시작 구분 | Unhealthy event, restart 증가 | 잘못된 liveness probe 제거/수정 | `deployment:nginx:running` | compiler → `liveness_probe` injector → K8s rule |
| `service_selector_mismatch` | selector와 endpoint 연결 진단 | Service endpoint 0, Pod는 정상 | Service selector를 target label과 일치시킴 | `service:webapp-svc:endpoints` | compiler → `service_misconfig` injector → K8s rule |
| `configmap_misconfig` | 설정 마운트와 애플리케이션 시작 실패 분석 | nginx config error, CrashLoopBackOff | 잘못된 ConfigMap 마운트/내용 정상화 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `init_container_failure` | init container와 main container lifecycle 구분 | Init:CrashLoopBackOff, init exit 1 | 실패 init container 설정 제거/수정 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `node_selector_mismatch` | scheduler event와 node selector 진단 | Pending, FailedScheduling | 불가능한 nodeSelector 제거/수정 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `compound_probe_cascade` | 순차적으로 드러나는 복합 장애 분석 | ImagePullBackOff 후 Ready 0/1 | image와 readiness probe를 모두 정상화 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `compound_crash_service` | 독립적인 workload/service 장애 분리 진단 | CrashLoopBackOff와 endpoint 0 동시 발생 | command와 Service selector를 각각 정상화 | deployment running AND service endpoints | compiler → 동일 injector → 복합 K8s rule |
| `wrong_image_registry` | registry 인증/경로 event 구분 | ImagePullBackOff, unauthorized event | 허용된 public/정상 이미지로 변경 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `secret_ref_missing` | Secret 참조 실패 진단 | CreateContainerConfigError, Secret not found | 허용 범위에서 참조 제거 또는 필요한 Secret 구성 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `pvc_unbound` | PVC binding과 Pod scheduling 관계 이해 | Pending PVC, volume binding event | 잘못된 volume/PVC 참조 제거 또는 지원 storage 설정 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |
| `cpu_throttle` | CPU limit과 readiness 저하 상관 분석 | CPU 제한, Ready 0/1, probe timeout | CPU request/limit과 probe를 안전 범위로 정상화 | `deployment:nginx:running` | compiler → 동일 injector → K8s rule |

### Kubernetes legacy alias

다음 값은 기존 고정 미션 및 내부 호환용이다. 새 AI scenario의 canonical fault로 생성하지 않는다.

| legacy value | canonical value |
|---|---|
| `pod_failure` | `image_pull_error` |
| `memory_stress` | `oom_killed` |
| `service_misconfig` | `service_selector_mismatch` |
| `network_latency` | `probe_failure` |

## 4. Docker 후보 taxonomy

모든 항목은 현재 비활성이다. BE-13/14에서 실제 action과 validator가 구현되고 통합 테스트가 통과한 항목만 allowed list에 승격한다.

| fault type | learning objective | observable signals | allowed recovery action | mechanical validator 계약 | 담당 작업 |
|---|---|---|---|---|---|
| `container_network_disconnect` | container network 연결과 endpoint 조사 | disconnected network, inspect network 누락, 통신 실패 | 지정 sandbox network에 container 재연결 | target container가 expected network에 연결되고 health check 성공 | BE-13, BE-14 |
| `volume_mount_error` | volume/bind mount와 권한 진단 | mount 누락, read/write 실패, permission denied | 허용된 volume/mount 설정과 권한 정상화 | expected mount 존재 및 sandbox read/write probe 성공 | BE-13, BE-14 |
| `container_oom` | container memory limit과 OOM 종료 분석 | OOMKilled, exit 137, restart/stop | sandbox quota 안에서 memory limit 정상화 후 재시작 | container running, OOMKilled 해제, health check 성공 | BE-13, BE-14 |
| `container_cpu_throttle` | CPU 제한과 응답 저하 분석 | 높은 throttle, 낮은 CPU quota, health 지연 | sandbox 정책 범위에서 CPU limit 정상화 | container healthy 및 CPU quota 최소 기준 충족 | BE-13, BE-14 |

금지 복구: host Docker socket 사용, 다른 사용자 DinD 접근, 무제한 privileged 실행.

## 5. Linux 후보 taxonomy

모든 항목은 현재 비활성이다. BE-17/18에서 container cgroup·ephemeral storage·PID 범위의 안전한 구현과 validator가 준비된 항목만 allowed list에 승격한다.

| fault type | learning objective | observable signals | allowed recovery action | mechanical validator 계약 | 담당 작업 |
|---|---|---|---|---|---|
| `linux_oom` | cgroup memory pressure와 OOM 종료 분석 | OOM/exit signal, memory pressure, workload 중단 | sandbox workload 종료 또는 제한된 memory 설정 정상화 | workload/service 정상화 및 OOM 반복 없음 | BE-17, BE-18 |
| `disk_io_stress` | disk usage와 I/O saturation 구분 | 높은 I/O wait, worker 실행, ephemeral usage 증가 | 지정 I/O worker 종료 및 훈련 파일 정리 | worker 종료, 사용량 임계치 이하, service 정상 | BE-17, BE-18 |
| `zombie_process` | zombie 상태와 parent reap 이해 | process state Z, zombie count 증가 | 교육용 parent/helper를 정상 종료·재시작 | 지정 zombie count 0 | BE-17, BE-18 |
| `orphan_process` | parent/child lifecycle과 re-parenting 이해 | PPID 변화, helper process 잔존 | 지정 helper process tree 정상 종료 | orphan helper 부재 및 service 정상 | BE-17, BE-18 |
| `service_failure` | service/process/log 기반 장애 조사 | service down, port 미청취, error log | sandbox가 제공하는 service 재시작 또는 설정 정상화 | process running, expected socket listening, health check 성공 | BE-17, BE-18 |

금지 복구: host kernel 설정 변경, host OOM 유발, host disk fill, sandbox 밖 process 제어. systemd/dmesg는 Linux image가 실제 제공할 때만 사용한다.

## 6. 승격 조건

Docker/Linux fault를 생성 허용 상태로 바꾸려면 다음 조건을 모두 충족해야 한다.

1. backend environment별 allowlist에 canonical fault가 등록된다.
2. declarative parameters가 compiler schema와 안전 상한을 통과한다.
3. environment 전용 injector의 inject/revert가 idempotent하다.
4. fault-specific mechanical validator가 unrelated healthy resource를 성공으로 판정하지 않는다.
5. 같은 environment fixture와 integration test가 통과한다.
6. AI knowledge metadata와 eval case가 동일한 taxonomy version을 사용한다.

## 7. 알려진 계약 차이

- 현재 `ScenarioService.ALLOWED_FAULT_TYPES`에는 Kubernetes legacy alias가 포함되어 있다. AI 생성 prompt는 canonical 15종만 사용하며, alias 제거는 backend 계약 변경 작업에서 처리한다.
- 현재 backend는 `IMPLEMENTED_ENVIRONMENTS=(kubernetes,)`이므로 Docker/Linux scenario 실행을 허용하면 안 된다.
- fault allowlist를 AI와 backend가 서로 다른 파일에서 관리하는 동안에는 backend allowlist/OpenAPI가 최종 기준이다.
