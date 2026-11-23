# AfterFail Docker 안전 복구 플레이북

- Environment: `docker`
- Fault types: `container_network_disconnect`, `volume_mount_error`, `container_oom`, `container_cpu_throttle`
- 작성/갱신: 2026-08-29
- 출처: [Docker container CLI](https://docs.docker.com/reference/cli/docker/container/), [Docker networking](https://docs.docker.com/engine/network/), [Docker storage](https://docs.docker.com/engine/storage/), [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)

## Symptoms

- 장애 유형을 모른 채 빠르게 복구해야 한다.
- 여러 설정이 의심되지만 어떤 변경이 안전한지 불명확하다.
- container가 running인데 health가 나쁘거나, stopped인데 원인이 남아 있다.

## Observations

아래 순서로 증거를 좁힌다.

1. **존재/상태**: `docker ps -a`
2. **구성/마지막 종료**: `docker inspect training-app`
3. **애플리케이션 증거**: `docker logs --tail 50 training-app`
4. **자원**: `docker stats --no-stream training-app`
5. **network**: `docker network inspect training-net`
6. **storage**: `docker volume inspect training-data`

모든 출력을 외부 AI에 그대로 보내지 않는다. secret, environment value, 내부 주소를
제거하고 상태·limit·network/mount 이름 등 필요한 관찰만 요약한다.

## Hypotheses

| 증거 | 우선 가설 | 다음 확인 |
|---|---|---|
| Networks에 `training-net` 없음 | network disconnect | network inspect endpoint |
| OOMKilled=true, exit 137 | memory limit/OOM | memory와 memory-swap |
| running, CPU quota 낮음, 지연 | CPU throttle | stats와 NanoCpus |
| volume 없음 | volume 생성 누락 | volume ls/inspect |
| volume 존재, Mounts 누락 | mount 계약 오류 | 직접 복구 불가 여부 |
| Exited, OOM=false | 일반 lifecycle/app 오류 | logs와 exit code |

## Safe commands

가설이 증거로 확인된 뒤 해당 최소 복구만 선택한다.

```bash
# network endpoint 누락
docker network connect training-net training-app

# CPU 상한 비정상
docker update --cpus 1 training-app

# memory 상한 비정상
docker update --memory 256m --memory-swap 256m training-app
docker start training-app

# 단순 중지 또는 pause
docker start training-app
docker unpause training-app

# 허용 volume 자체 누락
docker volume create training-data
```

volume mount attachment 변경은 실행 중 update로 해결할 수 없다. 현재 정책은 임의
`docker run`을 차단하므로 그 경우 원인과 관찰을 남기고 샌드박스 재프로비저닝을
요청한다. 불가능한 직접 복구를 성공으로 꾸미지 않는다.

## Recovery validation

복구 전과 같은 관찰을 반복하고 다음을 모두 확인한다.

- `training-app`이 안정적으로 running인가?
- 예상 `training-net` endpoint가 존재하는가?
- CPU/memory limit이 정상 계약인가?
- OOM/restart/error log가 반복되지 않는가?
- volume/mount가 필요한 scenario라면 실제 Mounts까지 정상인가?

하나라도 실패하면 다른 설정을 무작정 바꾸지 말고 가설 단계로 돌아간다. 최종 완료와
점수는 AI의 설명이 아니라 backend mechanical validator가 결정한다.

## Hint-level concepts

- Level 0: 사용자가 가진 증거와 아직 보지 않은 축을 질문한다.
- Level 1: 증거→가설 표에서 조사 방향만 안내한다.
- Level 2: read-only 명령을 제시하고 결과 해석을 요구한다.
- Level 3: 확인된 단일 fault의 최소 복구와 검증 순서를 제시한다.

## Sandbox safety boundary

다음은 항상 금지한다: host Docker socket mount, `docker -H/--host`, daemon context 변경,
`docker run/exec`, privileged container, 임의 image pull/build, 다른 사용자 resource 접근.
