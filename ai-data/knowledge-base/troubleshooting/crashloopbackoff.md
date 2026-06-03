# CrashLoopBackOff 트러블슈팅 가이드

## 개요

CrashLoopBackOff는 Kubernetes에서 가장 흔하게 발생하는 Pod 오류 중 하나입니다. Pod가 시작되었다가 계속 실패하고 재시작을 반복하는 상태를 의미합니다.

## 증상

- Pod 상태가 `CrashLoopBackOff`로 표시됨
- Pod가 반복적으로 재시작됨
- `RESTARTS` 카운트가 계속 증가함
- 애플리케이션에 접근할 수 없음

## 원인

### 1. 애플리케이션 오류
- 코드 버그로 인한 크래시
- 처리되지 않은 예외
- 메모리 부족 (OOM)
- 잘못된 설정 파일

### 2. 설정 문제
- 잘못된 환경 변수
- 누락된 ConfigMap 또는 Secret
- 잘못된 명령어 또는 인자

### 3. 리소스 문제
- 메모리 제한 초과
- CPU 제한 초과
- 디스크 공간 부족

### 4. 의존성 문제
- 데이터베이스 연결 실패
- 외부 서비스 연결 실패
- 필요한 파일이나 볼륨 누락

## 진단 방법

### 1. Pod 상태 확인

```bash
kubectl get pods
```

출력 예시:
```
NAME                    READY   STATUS             RESTARTS   AGE
myapp-5d4b7c9f8-xyz12   0/1     CrashLoopBackOff   5          3m
```

### 2. Pod 상세 정보 확인

```bash
kubectl describe pod <pod-name>
```

주요 확인 사항:
- **Events 섹션**: 가장 중요한 정보
- **State**: 현재 상태와 이전 상태
- **Last State**: 마지막 종료 이유
- **Exit Code**: 종료 코드 (0이 아니면 오류)

일반적인 Exit Code:
- `0`: 정상 종료
- `1`: 일반 오류
- `137`: OOMKilled (메모리 부족)
- `139`: Segmentation Fault
- `143`: SIGTERM (정상 종료 신호)

### 3. 로그 확인

현재 컨테이너 로그:
```bash
kubectl logs <pod-name>
```

이전 컨테이너 로그 (크래시 전):
```bash
kubectl logs <pod-name> --previous
```

실시간 로그 스트리밍:
```bash
kubectl logs <pod-name> -f
```

특정 컨테이너 로그 (멀티 컨테이너 Pod):
```bash
kubectl logs <pod-name> -c <container-name>
```

### 4. 리소스 사용량 확인

```bash
kubectl top pod <pod-name>
```

## 해결 방법

### 1. 로그 분석

**단계**:
1. `kubectl logs <pod-name> --previous`로 크래시 전 로그 확인
2. 에러 메시지, 스택 트레이스 찾기
3. 마지막 로그 라인 확인 (어디서 멈췄는지)

**예시**:
```
Error: Cannot connect to database at localhost:5432
    at Database.connect (/app/db.js:45:12)
    at Server.start (/app/server.js:23:8)
```

→ 데이터베이스 연결 문제

### 2. 설정 확인

**환경 변수 확인**:
```bash
kubectl exec <pod-name> -- env
```

**ConfigMap 확인**:
```bash
kubectl get configmap <configmap-name> -o yaml
```

**Secret 확인**:
```bash
kubectl get secret <secret-name> -o yaml
```

### 3. 리소스 제한 조정

메모리 부족 (OOMKilled) 시:
```yaml
resources:
  requests:
    memory: "256Mi"
  limits:
    memory: "512Mi"  # 증가
```

CPU 제한 문제 시:
```yaml
resources:
  requests:
    cpu: "100m"
  limits:
    cpu: "500m"  # 증가
```

### 4. 애플리케이션 수정

**Liveness Probe 조정**:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30  # 시작 시간 증가
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

**Readiness Probe 추가**:
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
```

### 5. 의존성 문제 해결

**데이터베이스 연결 확인**:
```bash
# Pod 내부에서 연결 테스트
kubectl exec <pod-name> -- nc -zv <db-host> <db-port>
```

**DNS 확인**:
```bash
kubectl exec <pod-name> -- nslookup <service-name>
```

## 실전 예제

### 예제 1: 환경 변수 누락

**증상**:
```
Error: DATABASE_URL is not defined
```

**해결**:
```yaml
env:
  - name: DATABASE_URL
    value: "postgresql://user:pass@db:5432/mydb"
```

### 예제 2: 메모리 부족 (OOMKilled)

**증상**:
```bash
kubectl describe pod myapp-xyz
# Last State: Terminated
# Reason: OOMKilled
# Exit Code: 137
```

**해결**:
```yaml
resources:
  limits:
    memory: "1Gi"  # 512Mi에서 증가
```

### 예제 3: 잘못된 명령어

**증상**:
```
Error: executable file not found in $PATH
```

**해결**:
```yaml
command: ["/app/server"]  # 올바른 경로로 수정
# 또는
command: ["node", "server.js"]
```

### 예제 4: ConfigMap 마운트 실패

**증상**:
```
Error: ENOENT: no such file or directory, open '/config/app.conf'
```

**해결**:
```yaml
volumeMounts:
  - name: config
    mountPath: /config
volumes:
  - name: config
    configMap:
      name: app-config  # ConfigMap이 존재하는지 확인
```

## 예방 방법

### 1. 적절한 Health Check 설정

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
```

### 2. 충분한 리소스 할당

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### 3. 로깅 강화

- 애플리케이션 시작 시 로그 출력
- 에러 발생 시 상세한 스택 트레이스
- 중요한 설정 값 로깅 (민감 정보 제외)

### 4. Graceful Shutdown 구현

```javascript
// Node.js 예제
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});
```

### 5. 의존성 체크

애플리케이션 시작 전 의존성 확인:
```javascript
async function checkDependencies() {
  try {
    await database.ping();
    await redis.ping();
    console.log('All dependencies are ready');
  } catch (error) {
    console.error('Dependency check failed:', error);
    process.exit(1);
  }
}
```

## 체크리스트

진단 시 확인할 사항:

- [ ] `kubectl get pods`로 Pod 상태 확인
- [ ] `kubectl describe pod`로 Events 확인
- [ ] `kubectl logs --previous`로 크래시 전 로그 확인
- [ ] Exit Code 확인 (137 = OOMKilled)
- [ ] 환경 변수 확인
- [ ] ConfigMap/Secret 존재 여부 확인
- [ ] 리소스 사용량 확인 (`kubectl top pod`)
- [ ] Liveness/Readiness Probe 설정 확인
- [ ] 의존성 서비스 연결 확인

## 추가 리소스

- [Kubernetes 공식 문서 - Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)
- [Kubernetes 공식 문서 - Debug Running Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/)
- [Exit Code 참조](https://tldp.org/LDP/abs/html/exitcodes.html)

## 요약

CrashLoopBackOff는 Pod가 반복적으로 실패하는 상태입니다. 해결을 위해:

1. **로그 확인**: `kubectl logs --previous`
2. **Events 확인**: `kubectl describe pod`
3. **Exit Code 확인**: 137 = OOMKilled
4. **설정 확인**: 환경 변수, ConfigMap, Secret
5. **리소스 확인**: 메모리/CPU 제한
6. **의존성 확인**: 데이터베이스, 외부 서비스 연결

대부분의 경우 로그와 Events에서 원인을 찾을 수 있습니다.
