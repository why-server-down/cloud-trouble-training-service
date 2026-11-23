# Linux 서비스 실패와 로그 조사

- Environment: `linux`
- Fault types: `service_failure`
- Primary sources: [proc_pid_status(5)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html), [systemd journal fields](https://www.freedesktop.org/software/systemd/man/latest/systemd.journal-fields.html)

## Symptoms

서비스 endpoint가 응답하지 않거나 프로세스가 반복 종료된다.

## Observations

프로세스 존재, 상태, 종료 시점의 애플리케이션 로그, listen socket을 순서대로 연결한다. sandbox 이미지에 systemd가 없을 수 있으므로 `systemctl`과 `journalctl`을 기본 전제로 삼지 않는다.

## Hypotheses

- 프로세스 부재는 시작 실패 또는 종료를 시사한다.
- 프로세스가 있어도 listen socket이나 readiness가 없으면 초기화 실패일 수 있다.
- 로그 한 줄보다 반복 패턴과 종료 시점을 본다.

## Safe commands

BE-16이 `ps`를 공개한 경우의 관찰 후보이다. 로그는 서버가 제공한 고정 helper를 우선한다.

```bash
ps -eo pid,ppid,stat,comm
```

## Recovery validation

프로세스만 살아난 것으로 끝내지 않고, 예상 socket, 애플리케이션 응답, validator를 확인한다.

## Hint-level concepts

1. process, log, socket 세 단서를 시간 순서로 연결한다.
2. service manager 존재 여부를 capability에서 확인한다.
3. 복구 후 기능 검증을 수행한다.

## Sandbox safety boundary

`systemctl`, `journalctl`, `dmesg`는 capability에 명시된 경우에만 안내한다. 호스트 journal/kernel log와 host PID namespace에는 접근하지 않는다.
