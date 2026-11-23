# Docker 조사 명령: ps, inspect, logs, stats

- Environment: `docker`
- Fault types: `general`
- 작성/갱신: 2026-08-29
- 출처: [docker logs](https://docs.docker.com/reference/cli/docker/container/logs/), [docker stats](https://docs.docker.com/reference/cli/docker/container/stats/), [Docker container CLI](https://docs.docker.com/reference/cli/docker/container/)

## Symptoms

- 사용자는 “컨테이너가 안 된다”는 현상만 알고 있다.
- 상태, 설정, 애플리케이션 로그, 자원 사용량 중 어느 층이 문제인지 불명확하다.
- 출력이 많아 중요한 단서를 놓치거나, 한 명령의 결과만으로 원인을 단정한다.

## Observations

각 명령은 서로 다른 질문에 답한다.

| 명령 | 답하는 질문 |
|---|---|
| `docker ps -a` | 대상이 존재하며 현재 상태가 무엇인가? |
| `docker inspect training-app` | network, mount, state, limit 같은 선언·런타임 설정은 무엇인가? |
| `docker logs --tail 50 training-app` | 프로세스가 stdout/stderr에 남긴 최근 증거는 무엇인가? |
| `docker stats --no-stream training-app` | 지금 CPU·memory·network·block I/O 사용량은 어떤가? |
| `docker port training-app` | container port가 어떻게 publish됐는가? |
| `docker top training-app` | 컨테이너 안에서 어떤 프로세스가 실행 중인가? |
| `docker diff training-app` | writable layer에서 어떤 경로가 바뀌었는가? |

`docker logs`는 애플리케이션이 stdout/stderr로 보낸 내용만 보여 준다. 로그가 비어 있다고
오류가 없다는 뜻은 아니다. `docker stats`는 흐르는 출력이므로 훈련에서는
`--no-stream`으로 한 시점의 값을 얻고, 필요하면 시간 간격을 두고 다시 비교한다.

## Hypotheses

1. `ps -a`에서 Exited → lifecycle 또는 OOM 가능성.
2. running이지만 log에 bind/listen 오류 → 애플리케이션/port 설정 가능성.
3. memory 사용량이 limit에 근접 → container OOM 가능성.
4. CPU가 지속적으로 상한에 붙음 → CPU quota가 지나치게 낮을 가능성.
5. inspect의 Networks에 `training-net`이 없음 → network disconnect 가능성.
6. inspect의 Mounts가 예상과 다름 → volume/mount 설정 가능성.

## Safe commands

```bash
docker ps -a
docker inspect training-app
docker logs --tail 50 training-app
docker stats --no-stream training-app
docker port training-app
docker top training-app
docker diff training-app
```

비밀 값이 로그나 inspect에 보일 수 있으므로 전체 출력을 채팅에 복사하지 않는다.
상태명, exit code, limit, network/mount 이름 등 필요한 관찰만 요약한다.

## Recovery validation

복구 명령 뒤에는 처음 사용한 관찰을 동일하게 반복한다. 기준이 바뀌면 전후 비교가
불가능하다. 상태 하나가 좋아진 것과 서비스가 정상화된 것을 구분한다.

```bash
docker ps
docker inspect training-app
docker stats --no-stream training-app
docker logs --tail 20 training-app
```

## Hint-level concepts

- Level 0: 상태·설정·로그·자원 중 어떤 증거가 부족한지 묻는다.
- Level 1: 명령 이름보다 각 관찰 축의 의미를 설명한다.
- Level 2: 가장 작은 read-only 명령 집합을 제시한다.
- Level 3: 관찰 결과를 가설과 연결하지만, unrelated 설정 변경은 권하지 않는다.

## Sandbox safety boundary

`docker exec`, `docker run`, `docker cp`, daemon host/context 변경은 허용되지 않는다.
호스트 Docker socket이나 privileged 실행을 진단 편의 수단으로 권장하지 않는다.
