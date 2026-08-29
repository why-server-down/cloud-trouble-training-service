# Linux CPU, 메모리와 load 관찰

- Environment: `linux`
- Fault types: `linux_oom`, `disk_io_stress`
- Primary sources: [proc_loadavg(5)](https://man7.org/linux/man-pages/man5/proc_loadavg.5.html), [proc_meminfo(5)](https://man7.org/linux/man-pages/man5/proc_meminfo.5.html), [Linux PSI](https://docs.kernel.org/accounting/psi.html)

## Symptoms

응답 지연, 처리량 저하, 메모리 부족 징후가 함께 나타난다.

## Observations

load average는 CPU 사용률과 동일하지 않다. 실행 대기뿐 아니라 중단 불가능한 대기 작업도 영향을 줄 수 있어 프로세스 상태와 PSI를 함께 본다. `/proc/meminfo`는 `free`의 기반이며, `MemAvailable`과 cgroup 제한을 구분한다.

## Hypotheses

- 높은 load와 CPU pressure는 runnable 경쟁 가능성을 높인다.
- 높은 load와 I/O pressure 및 `D` 상태는 I/O 병목 가능성을 높인다.
- 전체 `MemAvailable`이 충분해도 cgroup OOM은 발생할 수 있다.

## Safe commands

BE-16 capability가 제공할 때만 다음 읽기 명령을 사용한다.

```bash
free -m
ps -eo pid,ppid,stat,comm
```

## Recovery validation

한 시점의 숫자가 아니라 일정 시간 재관찰하고, pressure 감소와 validator 통과를 확인한다.

## Hint-level concepts

1. load, utilization, pressure를 같은 값으로 취급하지 않는다.
2. 시스템 범위와 cgroup 범위를 나눈다.
3. 증상과 시간적으로 맞는 지표를 선택한다.

## Sandbox safety boundary

`top`, `vmstat` 등 이미지에 없는 도구를 가정하지 않는다. nice 값, CPU affinity, sysctl 또는 cgroup 제한을 사용자가 직접 바꾸게 하지 않는다.
