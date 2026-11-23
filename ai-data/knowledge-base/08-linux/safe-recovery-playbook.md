# AfterFail Linux 안전 복구 플레이북

- Environment: `linux`
- Fault types: `linux_oom`, `disk_io_stress`, `zombie_process`, `orphan_process`, `service_failure`
- Primary sources: [cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html), [Linux PSI](https://docs.kernel.org/accounting/psi.html), [proc(5)](https://man7.org/linux/man-pages/man5/proc.5.html)

## Symptoms

Linux 미션의 공통 증상은 프로세스 누적/부재, OOM 종료, I/O 지연, 서비스 응답 실패다.

## Observations

환경 capability를 먼저 확인하고 증상별 최소 관찰만 수행한다. OOM은 cgroup event, I/O는 capacity와 PSI, 좀비/고아는 상태와 PPID, 서비스는 process-log-socket 순서로 증거를 모은다.

## Hypotheses

- `linux_oom`: cgroup limit과 `oom_kill` 변화
- `disk_io_stress`: 용량 부족 또는 I/O pressure
- `zombie_process`: 부모의 wait/reap 실패
- `orphan_process`: 예상 부모/supervisor 이탈
- `service_failure`: 시작 실패, 설정 오류 또는 listen 부재

## Safe commands

실제 명령은 세션 capability의 argv allowlist에 있는 읽기 명령만 사용한다.

```bash
ps -eo pid,ppid,stat,comm
free -m
df -h
ss -lnt
```

## Recovery validation

서버가 미션별로 제공한 고정 복구 동작을 사용하고 동일 지표를 재관찰한다. 마지막 판정은 프로세스 존재 하나가 아니라 기계적 validator 결과로 한다.

## Hint-level concepts

1. capability 확인
2. 증상 범위 축소
3. 단일 가설을 안전하게 검증
4. 허용된 복구 동작 수행
5. 재관찰과 validator 확인

## Sandbox safety boundary

호스트 상태 변경, 권한 상승, namespace 진입, mount, sysctl, 임의 signal, 임의 삭제를 금지한다. `systemctl`, `journalctl`, `dmesg`, `ss`를 포함한 모든 선택 도구는 capability에 실제 노출된 경우에만 사용한다.
