# Linux 네트워크 socket 관찰

- Environment: `linux`
- Fault types: `service_failure`
- Primary sources: [ss(8)](https://man7.org/linux/man-pages/man8/ss.8.html), [proc_net(5)](https://man7.org/linux/man-pages/man5/proc_pid_net.5.html)

## Symptoms

서비스 프로세스는 실행 중이지만 연결이 거절되거나 timeout이 발생한다.

## Observations

예상 포트의 LISTEN 여부, bind 주소, 연결 상태를 본다. `ss`는 socket 통계를 제공하지만 이미지에 설치되지 않을 수 있다. `/proc/net`의 보이는 내용도 현재 process network namespace에 한정해야 한다.

## Hypotheses

- LISTEN 부재면 서비스 초기화 또는 설정 실패를 의심한다.
- loopback에만 bind되면 다른 sandbox 구성요소에서 접근하지 못할 수 있다.
- LISTEN이 정상인데 실패하면 호출 경로와 애플리케이션 상태를 추가 조사한다.

## Safe commands

BE-16 capability가 `ss`를 공개한 경우에만 사용한다.

```bash
ss -lnt
```

## Recovery validation

예상 주소와 포트의 LISTEN, 실제 요청 성공, validator 통과를 확인한다.

## Hint-level concepts

1. process 존재와 socket listen을 분리한다.
2. 주소, 포트, namespace를 확인한다.
3. 관찰 결과를 서비스 설정과 연결한다.

## Sandbox safety boundary

`iptables`, `ip netns`, `nsenter`, packet capture는 안내하지 않는다. 호스트 network namespace나 다른 사용자 sandbox를 조사하지 않는다.
