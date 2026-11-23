# Linux 디스크 용량과 I/O 포화 조사

- Environment: `linux`
- Fault types: `disk_io_stress`
- Primary sources: [Linux PSI](https://docs.kernel.org/accounting/psi.html), [proc(5)](https://man7.org/linux/man-pages/man5/proc.5.html)

## Symptoms

파일 작업과 요청이 느려지고 timeout이 늘거나 쓰기가 실패한다.

## Observations

용량 부족과 I/O 포화를 분리한다. `df`는 filesystem 사용량, `du`는 디렉터리 사용량 관찰 후보이다. PSI가 제공되면 `/proc/pressure/io`의 `some`과 `full` 평균으로 작업이 I/O 때문에 멈춘 시간 비율을 본다.

## Hypotheses

- filesystem이 가득 찼다면 쓰기 실패가 핵심이다.
- 여유 공간이 있는데 I/O PSI가 높으면 장치 경합 또는 과도한 작업을 의심한다.
- load average 상승만으로 CPU 문제라고 단정하지 않는다.

## Safe commands

다음 후보는 BE-16 allowlist에 실제 공개된 경우에만 사용한다.

```bash
df -h
du -sh /workspace
```

## Recovery validation

복구 후 충분한 여유 공간, I/O pressure 감소, 대상 서비스 응답과 validator 통과를 모두 확인한다.

## Hint-level concepts

1. 먼저 capacity와 latency를 분리한다.
2. PSI의 `some`과 `full`을 구분한다.
3. 임의 삭제보다 미션이 지정한 안전한 정리 동작을 선택한다.

## Sandbox safety boundary

`dd`, `fio`, `stress-ng`, mount, raw device 접근과 임의 파일 삭제는 금지한다. `/proc/pressure/io`도 capability가 노출할 때만 읽는다.
