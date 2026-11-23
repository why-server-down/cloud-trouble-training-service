# Docker memory OOM과 CPU throttle 트러블슈팅

- Environment: `docker`
- Fault types: `container_oom`, `container_cpu_throttle`
- 작성/갱신: 2026-08-29
- 출처: [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/), [docker stats](https://docs.docker.com/reference/cli/docker/container/stats/)

## Symptoms

- `training-app`이 exit code 137로 종료되고 `OOMKilled=true`다.
- container가 running이지만 응답이 지속적으로 느리다.
- CPU 사용률이 할당 상한에 붙거나 latency가 급증한다.
- memory limit 변경 후 start가 실패한다.

## Observations

memory OOM과 CPU throttle은 모두 “느림/중단”을 만들지만 증거가 다르다.
OOM은 프로세스 종료와 state 전환을 만들 수 있고, CPU throttle은 대개 container를
running 상태로 유지한 채 처리 시간을 늘린다.

```bash
docker ps -a
docker inspect training-app
docker stats --no-stream training-app
docker logs --tail 50 training-app
docker top training-app
```

memory는 현재 사용량뿐 아니라 limit, swap limit, `OOMKilled`, exit code를 함께 본다.
CPU는 한 번의 순간값만으로 단정하지 말고 반복 관찰과 설정된 NanoCpus/CPU quota를
대조한다. `docker stats`의 memory 값은 Linux cache 처리 방식 때문에 raw cgroup 값과
차이가 날 수 있으므로 비율 하나만으로 OOM을 확정하지 않는다.

## Hypotheses

1. memory hard limit이 workload의 정상 working set보다 낮다.
2. memory leak 또는 순간 spike가 limit을 넘었다.
3. memory와 memory-swap의 관계가 잘못되어 update/start가 실패한다.
4. `--cpus`가 지나치게 낮아 CFS quota에 의해 처리량이 제한된다.
5. 실제 원인은 애플리케이션 오류인데 resource 문제로 오인했다.

## Safe commands

AfterFail 기본 정상 CPU 상한은 `1`이며, 훈련 자원 범위 안에서만 조정한다.

```bash
docker update --cpus 1 training-app
docker update --memory 256m --memory-swap 256m training-app
docker start training-app
```

`--memory-swap`은 memory와 swap의 합계 상한이다. 두 값을 함께 변경할 때는
memory-swap이 memory보다 작지 않아야 한다. 무제한 swap이나 OOM killer 비활성화는
host 안정성을 해칠 수 있어 사용하지 않는다. 관찰된 장애가 CPU인 경우 memory까지
함께 바꾸지 않는 최소 변경 원칙을 적용한다.

## Recovery validation

```bash
docker inspect training-app
docker stats --no-stream training-app
docker ps
docker logs --tail 20 training-app
```

- CPU scenario는 NanoCpus/CPU quota가 정상 계약으로 돌아왔는가?
- OOM scenario는 `OOMKilled` 반복과 exit 137이 멈췄는가?
- container가 running이고 응답 지연이 회복됐는가?
- 자원 상한이 샌드박스 quota를 넘지 않는가?

## Hint-level concepts

- Level 0: 종료됐는지 느리기만 한지 구분하도록 질문한다.
- Level 1: State/OOMKilled와 stats/limit의 관계를 설명한다.
- Level 2: read-only 관찰 명령과 최소 변경 후보를 분리한다.
- Level 3: 확인된 fault에 해당하는 한 가지 limit만 정상 계약으로 복원한다.

## Sandbox safety boundary

host cgroup, kernel scheduler, Docker daemon 설정을 변경하지 않는다. `docker run`,
privileged 실행, host Docker socket을 사용하지 않으며 `training-app`만 수정한다.
