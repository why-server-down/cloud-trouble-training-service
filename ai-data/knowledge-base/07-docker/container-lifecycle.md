# Docker 컨테이너 생명주기와 종료 상태

- Environment: `docker`
- Fault types: `container_oom`, `container_cpu_throttle`
- 작성/갱신: 2026-08-29
- 출처: [Docker container CLI](https://docs.docker.com/reference/cli/docker/container/), [docker ps](https://docs.docker.com/reference/cli/docker/container/ls/)

## Symptoms

- `training-app`이 요청에 응답하지 않는다.
- `docker ps`에는 대상이 없지만 `docker ps -a`에는 `Exited`로 보인다.
- 상태가 `Restarting`, `Paused`, `Exited (137)` 중 하나다.
- 재시작해도 다시 종료되거나 응답이 늦다.

## Observations

먼저 “컨테이너가 존재하는가”, “실행 중인가”, “왜 마지막에 끝났는가”를 분리한다.
이미지는 실행 정의이고 컨테이너는 그 정의의 실행 인스턴스이므로, 컨테이너가 멈췄다고
이미지 자체가 손상됐다고 단정할 수 없다.

```bash
docker ps
docker ps -a
docker inspect training-app
docker logs --tail 50 training-app
docker top training-app
```

`docker inspect`에서는 `.State.Status`, `.State.ExitCode`, `.State.OOMKilled`,
`.State.Error`, `.RestartCount`를 함께 본다. 종료 코드 `137`은 SIGKILL과 연결되지만,
그 값만으로 OOM을 확정하지 말고 `OOMKilled` 및 memory limit을 함께 확인한다.

## Hypotheses

1. `Exited`이고 exit code가 0이면 작업이 정상 종료됐지만 지속 실행 서비스 설정이 아닐 수 있다.
2. `Exited`이고 `OOMKilled=true`이면 memory limit과 사용량을 조사한다.
3. `Restarting`이면 restart policy가 작동 중이며 로그의 반복 오류가 원인일 수 있다.
4. `Paused`이면 프로세스가 종료된 것이 아니라 스케줄링이 정지된 상태다.
5. `running`인데 응답이 없으면 network, port, CPU throttle을 별도로 조사한다.

## Safe commands

AfterFail Docker 샌드박스에서는 아래 복구만 훈련 대상에 허용된다.

```bash
docker start training-app
docker restart training-app
docker unpause training-app
```

관찰 없이 재시작부터 하면 원인 증거가 사라질 수 있다. `ps -a → inspect → logs` 순서로
상태를 기록한 뒤, 원인이 단순 중지 또는 pause일 때만 생명주기 명령을 선택한다.

## Recovery validation

```bash
docker ps
docker inspect training-app
docker logs --tail 20 training-app
```

- `training-app`이 `running`이어야 한다.
- restart loop 없이 상태가 안정적으로 유지돼야 한다.
- 최근 로그에 동일한 치명 오류가 반복되지 않아야 한다.
- network와 resource 문제가 남아 있으면 “실행 중”만으로 복구 완료로 판단하지 않는다.

## Hint-level concepts

- Level 0: 실행 여부와 종료 원인을 구분하도록 질문한다.
- Level 1: `ps -a`, State, exit code, OOMKilled의 관계를 안내한다.
- Level 2: 관찰 명령을 제시하되 바로 `start`를 정답으로 주지 않는다.
- Level 3: 관찰 결과가 단순 중지임을 확인한 경우에만 안전한 시작 명령을 제시한다.

## Sandbox safety boundary

호스트 Docker socket, `docker -H`, `docker run`, `docker exec`, privileged container를
사용하지 않는다. 모든 명령은 사용자 전용 DinD 안의 `training-app`에만 적용한다.
