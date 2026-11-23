# Linux 프로세스 상태, 좀비와 고아 프로세스

- Environment: `linux`
- Fault types: `zombie_process`, `orphan_process`
- Primary sources: [proc_pid_stat(5)](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html), [wait(2)](https://man7.org/linux/man-pages/man2/waitpid.2.html)

## Symptoms

프로세스 수가 계속 늘거나 새 프로세스 생성이 실패한다. 종료한 자식이 남아 있거나 부모가 사라진 프로세스가 관찰된다.

## Observations

`/proc/<pid>/stat`의 상태 `Z`는 zombie이며 네 번째 필드는 PPID다. 좀비는 종료했지만 부모가 `wait` 계열 호출로 회수하지 않은 자식이다. 고아 프로세스는 부모 종료 뒤 init 또는 subreaper에 입양되므로, PPID 변화 자체와 서비스 의도를 함께 본다.

## Hypotheses

- `Z`가 반복되면 부모의 자식 회수 로직이 빠졌을 수 있다.
- PPID가 예상 supervisor와 다르면 부모 비정상 종료 또는 잘못된 daemonization을 의심한다.
- 잠깐 보이는 단일 `Z`만으로 장애를 확정하지 않는다.

## Safe commands

아래는 BE-16 capability에 `ps`가 공개된 경우에만 사용할 후보 명령이다.

```bash
ps -eo pid,ppid,stat,comm
```

## Recovery validation

복구 뒤 동일 관찰을 반복해 `Z` 누적이 멈췄는지, 대상 프로세스의 PPID가 기대 supervisor인지, 서비스 validator가 통과하는지 확인한다.

## Hint-level concepts

1. 상태 문자와 PPID를 먼저 찾는다.
2. 좀비를 직접 종료하려 하지 말고 부모의 회수 책임을 추적한다.
3. 최종 답은 부모/감시 프로세스의 안전한 복구와 validator 결과다.

## Sandbox safety boundary

호스트 PID namespace는 노출하지 않는다. `kill`, `pkill`, `nsenter`는 예시로 제공하지 않으며 복구는 서버가 허용한 고정 동작만 사용한다.
