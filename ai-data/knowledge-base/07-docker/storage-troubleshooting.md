# Docker volume과 bind mount 트러블슈팅

- Environment: `docker`
- Fault types: `volume_mount_error`
- 작성/갱신: 2026-08-29
- 출처: [Docker storage](https://docs.docker.com/engine/storage/), [Docker volumes](https://docs.docker.com/engine/storage/volumes/), [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)

## Symptoms

- 애플리케이션이 예상 파일을 찾지 못한다.
- mount 경로에서 permission denied 또는 read-only 오류가 난다.
- container 재시작 후 데이터가 사라졌다고 보인다.
- `training-data` volume이 없거나 container의 Mounts에 연결되지 않았다.

## Observations

container writable layer, Docker-managed volume, bind mount를 구분한다.
volume은 Docker가 daemon 내부에서 관리하고, bind mount는 daemon host의 특정 경로에
의존한다. AfterFail의 Docker daemon은 사용자 전용 DinD 안에 있으므로 “host”는 사용자
PC가 아니라 해당 sandbox Pod 내부 daemon 환경을 뜻한다.

```bash
docker inspect training-app
docker volume ls
docker volume inspect training-data
docker diff training-app
docker logs --tail 50 training-app
```

- inspect의 Mounts에 source/name, destination, mode, RW가 어떻게 보이는가?
- 파일 변경이 writable layer에만 생겼는가?
- 오류가 mount 누락인지, 권한인지, read-only mode인지 구분했는가?
- volume 존재와 container attachment를 같은 것으로 오해하지 않았는가?

## Hypotheses

1. `training-data` volume 자체가 없다.
2. volume은 있지만 `training-app`에 attach되지 않았다.
3. destination이 애플리케이션이 읽는 경로와 다르다.
4. read-only mode 또는 파일 소유권 때문에 쓰기가 실패한다.
5. bind source가 존재하지 않거나 DinD daemon에서 접근할 수 없다.

## Safe commands

훈련 정책은 이름이 허용된 volume의 조회와 생성을 허용한다.

```bash
docker volume ls
docker volume inspect training-data
docker volume create training-data
```

중요: volume을 생성해도 실행 중인 container에 새 mount가 자동으로 붙지 않는다.
Docker는 실행 중 container의 mount 구성을 `docker update`로 바꾸지 못한다. 현재
AfterFail 정책은 임의 image 실행을 막기 위해 `docker run`을 차단하므로, mount 자체가
잘못된 시나리오는 사용자가 안전하게 완결 복구할 수 없다. 이 경우 상태와 원인을
보고하고 세션/샌드박스 재프로비저닝 경로를 사용해야 한다.

## Recovery validation

```bash
docker volume inspect training-data
docker inspect training-app
docker logs --tail 20 training-app
```

- volume이 존재하는가?
- Mounts의 destination과 RW mode가 기대 계약과 일치하는가?
- 애플리케이션의 파일 접근 오류가 사라졌는가?
- mount attachment가 여전히 틀리면 복구 완료로 표시하지 않는다.

## Hint-level concepts

- Level 0: 데이터가 어느 storage layer에 있어야 하는지 질문한다.
- Level 1: volume 존재와 attachment의 차이를 설명한다.
- Level 2: inspect와 volume inspect를 함께 제시한다.
- Level 3: 현재 정책에서 안전한 직접 복구가 불가능하면 그 제한을 명시한다.

## Sandbox safety boundary

호스트 경로, `/var/run/docker.sock`, `/` bind mount, privileged container를 권장하지 않는다.
`docker run`, `docker rm`, 임의 volume 삭제로 정책을 우회하지 않는다.
