# Linux cgroup OOM 조사

- Environment: `linux`
- Fault types: `linux_oom`
- Primary sources: [cgroup v2 memory controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory)

## Symptoms

프로세스가 갑자기 종료되거나 재시작되고, 메모리 할당 실패 또는 응답 중단이 나타난다.

## Observations

cgroup v2의 `memory.current`는 현재 사용량, `memory.max`는 hard limit다. `memory.events`의 `oom`은 할당이 실패 직전까지 간 횟수이고 `oom_kill`은 OOM killer가 해당 cgroup 프로세스를 종료한 횟수다. 카운터 변화와 애플리케이션 종료 시점을 함께 비교한다.

## Hypotheses

- `memory.current`가 `memory.max`에 근접하고 `oom_kill`이 증가하면 cgroup 한도 초과 가능성이 높다.
- 호스트 여유 메모리만 보고 컨테이너 OOM을 배제할 수 없다.
- `oom` 증가 없이 종료됐다면 일반 오류나 supervisor 동작을 별도로 조사한다.

## Safe commands

BE-16이 읽기 전용 cgroup helper 또는 `free`를 제공할 때만 사용한다.

```bash
free -m
```

## Recovery validation

서버가 제공한 복구 동작 후 `oom_kill` 기준값이 더 증가하지 않고 프로세스와 서비스 validator가 안정적으로 통과하는지 확인한다.

## Hint-level concepts

1. 전체 메모리와 cgroup 한도를 구분한다.
2. 사용량 한 번보다 event counter의 변화를 본다.
3. 원인 프로세스와 제한값 중 무엇이 비정상인지 판별한다.

## Sandbox safety boundary

호스트 cgroup을 mount하거나 수정하지 않는다. `memory.max`, sysctl, swap 설정 변경은 허용하지 않으며 cgroup 파일 경로는 capability가 제공한 대상만 읽는다.
