# Docker bridge network 트러블슈팅

- Environment: `docker`
- Fault types: `container_network_disconnect`
- 작성/갱신: 2026-08-29
- 출처: [Docker bridge network driver](https://docs.docker.com/engine/network/drivers/bridge/), [Docker networking overview](https://docs.docker.com/engine/network/), [docker network connect](https://docs.docker.com/reference/cli/docker/network/connect/)

## Symptoms

- `training-app`은 running이지만 다른 훈련 구성요소와 통신하지 못한다.
- container 이름으로 연결할 때 DNS 오류 또는 connection refused가 발생한다.
- 예상 port가 보이지 않거나 network inspect에 endpoint가 없다.
- 재시작 후에도 통신이 회복되지 않는다.

## Observations

Docker network 문제를 network 연결, 이름 해석, port/listener의 세 층으로 나눈다.
사용자 정의 bridge에서는 같은 network의 container끼리 이름 또는 alias로 해석할 수 있다.
container가 network에서 분리되면 애플리케이션 프로세스가 정상이어도 그 경로는 사라진다.

```bash
docker ps
docker inspect training-app
docker network ls
docker network inspect training-net
docker port training-app
docker logs --tail 50 training-app
```

- `docker inspect training-app`의 Networks에 `training-net`이 있는가?
- `docker network inspect training-net`의 Containers에 `training-app` endpoint가 있는가?
- port publish 정보와 애플리케이션이 실제 listen하는 port가 일치하는가?
- 로그의 DNS 실패와 connection refused를 구분했는가?

DNS 실패는 이름을 주소로 바꾸지 못한 것이고, connection refused는 주소에 도달했지만
해당 port에서 수신하는 프로세스가 없을 가능성이 크다. 둘을 같은 문제로 처리하지 않는다.

## Hypotheses

1. `training-app`이 `training-net`에서 disconnect됐다.
2. container는 network에 있지만 기대한 이름/alias가 다르다.
3. network는 정상이나 애플리케이션이 다른 port에서 listen한다.
4. container port는 열렸지만 외부 접근에 필요한 publish 설정이 없다.
5. 프로세스가 중지되어 network 증상처럼 보인다.

## Safe commands

현재 훈련의 network 복구 대상은 `training-net`과 `training-app`뿐이다.

```bash
docker network connect training-net training-app
```

연결 전에는 반드시 두 inspect 결과로 endpoint 누락을 확인한다. 임의 network 생성,
host network 사용, daemon iptables 변경은 훈련 범위를 벗어난다.

## Recovery validation

```bash
docker inspect training-app
docker network inspect training-net
docker ps
docker logs --tail 20 training-app
```

- 양쪽 inspect에서 동일 endpoint가 보여야 한다.
- container가 running이어야 한다.
- DNS/연결 실패 로그가 더 이상 반복되지 않아야 한다.
- network 연결만으로 애플리케이션 health가 회복되지 않으면 lifecycle/port 가설을 다시 본다.

## Hint-level concepts

- Level 0: 프로세스 상태와 network membership 중 무엇을 확인했는지 묻는다.
- Level 1: 사용자 정의 bridge와 network-scoped DNS 개념을 설명한다.
- Level 2: container/network 양쪽 inspect를 제시한다.
- Level 3: endpoint 누락이 확인된 경우에만 connect 명령을 제시한다.

## Sandbox safety boundary

호스트 network, Docker socket mount, `docker -H`, `docker run --privileged`를 사용하지 않는다.
다른 사용자 또는 임의 container/network 이름에 명령을 적용하지 않는다.
