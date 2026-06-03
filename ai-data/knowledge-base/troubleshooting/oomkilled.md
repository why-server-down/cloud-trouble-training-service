# OOMKilled 트러블슈팅 가이드

## 개요

OOMKilled (Out Of Memory Killed)는 컨테이너가 할당된 메모리 제한을 초과하여 Kubernetes가 강제로 종료시킨 상태입니다. Linux 커널의 OOM Killer가 메모리 부족 상황에서 프로세스를 종료시킵니다.

## 증상

- Pod가 반복적으로 재시작됨
- Pod 상태가 `CrashLoopBackOff`로 표시됨
- Exit Code가 `137`
- Events에 "OOMKilled" 메시지
- 애플리케이션이 갑자기 종료됨

## 원인

### 1. 메모리 제한 부족
- 설정된 메모리 limit이 너무 낮음
- 애플리케이션의 실제 메모리 사용량이 예상보다 높음

### 2. 메모리 누수 (Memory Leak)
- 애플리케이션 코드의 버그
- 사용하지 않는 객체가 메모리에 계속 남아있음
- 캐시가 무한정 증가

### 3. 트래픽 급증
- 갑작스러운 요청 증가
- 대용량 데이터 처리
- 동시 연결 수 증가

### 4. 비효율적인 코드
- 대용량 파일을 메모리에 로드
- 불필요한 데이터 복사
- 비효율적인 알고리즘

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

**중요한 정보**:
```
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
  Started:      Mon, 01 Jun 2026 10:00:00 +0000
  Finished:     Mon, 01 Jun 2026 10:01:30 +0000

Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Warning  BackOff    2m (x5 over 3m)    kubelet            Back-off restarting failed container
  Normal   Killing    1m                 kubelet            Container myapp failed liveness probe, will be restarted
```

**Exit Code 137의 의미**:
- 128 + 9 (SIGKILL) = 137
- 프로세스가 강제로 종료됨 (OOM Killer)

### 3. 메모리 사용량 확인

현재 메모리 사용량:
```bash
kubectl top pod <pod-name>
```

출력 예시:
```
NAME                    CPU(cores)   MEMORY(bytes)
myapp-5d4b7c9f8-xyz12   100m         512Mi
```

메모리 제한 확인:
```bash
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].resources}'
```

### 4. 메모리 사용 추이 확인

Metrics Server가 설치되어 있다면:
```bash
# 실시간 모니터링
kubectl top pod <pod-name> --containers

# 여러 Pod 비교
kubectl top pods -l app=myapp
```

### 5. 로그 확인

OOM 발생 전 로그:
```bash
kubectl logs <pod-name> --previous --tail=100
```

## 해결 방법

### 1. 메모리 제한 증가

**현재 설정 확인**:
```bash
kubectl get deployment <deployment-name> -o yaml | grep -A 10 resources
```

**메모리 제한 증가**:
```yaml
# 기존 설정
resources:
  requests:
    memory: "256Mi"
  limits:
    memory: "512Mi"  # OOMKilled 발생

# 수정 후
resources:
  requests:
    memory: "512Mi"
  limits:
    memory: "1Gi"  # 2배 증가
```

명령어로 수정:
```bash
kubectl set resources deployment <deployment-name> \
  --limits=memory=1Gi \
  --requests=memory=512Mi
```

**주의사항**:
- requests는 최소 보장 메모리
- limits는 최대 사용 가능 메모리
- limits를 초과하면 OOMKilled 발생

### 2. 메모리 누수 진단 및 수정

**메모리 프로파일링**:

Node.js 예제:
```javascript
// Heap snapshot 생성
const v8 = require('v8');
const fs = require('fs');

function takeHeapSnapshot() {
  const filename = `heap-${Date.now()}.heapsnapshot`;
  const snapshot = v8.writeHeapSnapshot(filename);
  console.log(`Heap snapshot written to ${snapshot}`);
}

// 주기적으로 스냅샷 생성
setInterval(takeHeapSnapshot, 60000); // 1분마다
```

Python 예제:
```python
import tracemalloc

# 메모리 추적 시작
tracemalloc.start()

# 애플리케이션 코드...

# 메모리 사용량 확인
current, peak = tracemalloc.get_traced_memory()
print(f"Current memory: {current / 1024 / 1024:.2f} MB")
print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")

# Top 10 메모리 사용처
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

**일반적인 메모리 누수 패턴**:

1. **전역 변수에 데이터 축적**:
```javascript
// 나쁜 예
const cache = {};
app.get('/data/:id', (req, res) => {
  cache[req.params.id] = fetchData(req.params.id); // 계속 증가
  res.json(cache[req.params.id]);
});

// 좋은 예 (LRU 캐시 사용)
const LRU = require('lru-cache');
const cache = new LRU({ max: 500, maxAge: 1000 * 60 * 60 });
```

2. **이벤트 리스너 미제거**:
```javascript
// 나쁜 예
function setupListener() {
  eventEmitter.on('data', handleData); // 계속 추가됨
}

// 좋은 예
function setupListener() {
  eventEmitter.removeListener('data', handleData);
  eventEmitter.on('data', handleData);
}
```

3. **타이머 미정리**:
```javascript
// 나쁜 예
setInterval(() => {
  // 작업...
}, 1000); // 정리되지 않음

// 좋은 예
const intervalId = setInterval(() => {
  // 작업...
}, 1000);

process.on('SIGTERM', () => {
  clearInterval(intervalId);
});
```

### 3. 애플리케이션 최적화

**대용량 파일 처리**:
```javascript
// 나쁜 예 - 전체 파일을 메모리에 로드
const data = fs.readFileSync('large-file.txt', 'utf8');
processData(data);

// 좋은 예 - 스트리밍 처리
const stream = fs.createReadStream('large-file.txt');
stream.on('data', (chunk) => {
  processChunk(chunk);
});
```

**데이터베이스 쿼리 최적화**:
```javascript
// 나쁜 예 - 모든 데이터를 메모리에 로드
const allUsers = await User.findAll(); // 수백만 건

// 좋은 예 - 페이지네이션
const users = await User.findAll({
  limit: 100,
  offset: page * 100
});

// 또는 스트리밍
const stream = User.findAll({ stream: true });
stream.on('data', (user) => {
  processUser(user);
});
```

**캐시 크기 제한**:
```javascript
const LRU = require('lru-cache');

const cache = new LRU({
  max: 500,              // 최대 항목 수
  maxAge: 1000 * 60 * 60, // 1시간 TTL
  length: (n, key) => n.length + key.length,
  dispose: (key, n) => {
    // 항목 제거 시 정리 작업
  }
});
```

### 4. Horizontal Pod Autoscaling (HPA)

트래픽 증가 시 자동으로 Pod 수 증가:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70  # 70% 사용 시 스케일 아웃
```

### 5. Vertical Pod Autoscaling (VPA)

자동으로 메모리 제한 조정:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: myapp-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  updatePolicy:
    updateMode: "Auto"  # 자동으로 리소스 조정
  resourcePolicy:
    containerPolicies:
    - containerName: myapp
      minAllowed:
        memory: "256Mi"
      maxAllowed:
        memory: "2Gi"
```

## 실전 예제

### 예제 1: 메모리 제한 부족

**증상**:
```bash
kubectl describe pod myapp-xyz
# Last State: Terminated
# Reason: OOMKilled
# Exit Code: 137
```

**해결**:
```bash
# 현재 메모리 사용량 확인
kubectl top pod myapp-xyz
# MEMORY: 480Mi (limit: 512Mi)

# 메모리 제한 증가
kubectl set resources deployment myapp --limits=memory=1Gi
```

### 예제 2: 메모리 누수

**증상**:
- 시간이 지날수록 메모리 사용량 증가
- 주기적으로 OOMKilled 발생

**진단**:
```javascript
// 메모리 사용량 로깅 추가
setInterval(() => {
  const used = process.memoryUsage();
  console.log({
    rss: `${Math.round(used.rss / 1024 / 1024)} MB`,
    heapTotal: `${Math.round(used.heapTotal / 1024 / 1024)} MB`,
    heapUsed: `${Math.round(used.heapUsed / 1024 / 1024)} MB`,
    external: `${Math.round(used.external / 1024 / 1024)} MB`,
  });
}, 10000);
```

**해결**:
- 코드 리뷰 및 메모리 누수 수정
- LRU 캐시 도입
- 이벤트 리스너 정리

### 예제 3: 대용량 파일 처리

**증상**:
- 파일 업로드/처리 시 OOMKilled
- 특정 API 호출 시 메모리 급증

**해결**:
```javascript
// 스트리밍 처리로 변경
const multer = require('multer');
const upload = multer({ dest: '/tmp/uploads/' });

app.post('/upload', upload.single('file'), async (req, res) => {
  const stream = fs.createReadStream(req.file.path);
  
  // 스트리밍으로 처리
  await processFileStream(stream);
  
  // 임시 파일 삭제
  fs.unlinkSync(req.file.path);
  
  res.json({ success: true });
});
```

## 모니터링 및 알림

### Prometheus + Grafana

메모리 사용량 모니터링:
```yaml
# Prometheus 쿼리
container_memory_usage_bytes{pod=~"myapp-.*"}
container_memory_working_set_bytes{pod=~"myapp-.*"}

# 메모리 사용률
(container_memory_usage_bytes / container_spec_memory_limit_bytes) * 100
```

### 알림 설정

```yaml
# PrometheusRule
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: memory-alerts
spec:
  groups:
  - name: memory
    rules:
    - alert: HighMemoryUsage
      expr: |
        (container_memory_usage_bytes / container_spec_memory_limit_bytes) > 0.9
      for: 5m
      annotations:
        summary: "High memory usage detected"
        description: "Pod {{ $labels.pod }} is using {{ $value }}% of memory limit"
```

## 예방 방법

### 1. 적절한 메모리 제한 설정

```yaml
resources:
  requests:
    memory: "512Mi"  # 평균 사용량 + 20%
  limits:
    memory: "1Gi"    # 피크 사용량 + 30%
```

### 2. 메모리 프로파일링 정기 실행

```bash
# 주기적으로 메모리 사용량 확인
kubectl top pods -l app=myapp --sort-by=memory
```

### 3. 로드 테스트

```bash
# Apache Bench
ab -n 10000 -c 100 http://myapp/api/endpoint

# k6
k6 run --vus 100 --duration 30s load-test.js
```

### 4. 코드 리뷰 체크리스트

- [ ] 전역 변수에 데이터 축적하지 않는가?
- [ ] 이벤트 리스너를 제거하는가?
- [ ] 타이머를 정리하는가?
- [ ] 대용량 파일을 스트리밍으로 처리하는가?
- [ ] 캐시 크기를 제한하는가?
- [ ] 데이터베이스 쿼리를 페이지네이션하는가?

## 체크리스트

진단 시 확인할 사항:

- [ ] Exit Code가 137인지 확인
- [ ] `kubectl describe pod`로 OOMKilled 확인
- [ ] `kubectl top pod`로 메모리 사용량 확인
- [ ] 메모리 limits 설정 확인
- [ ] 로그에서 메모리 관련 경고 확인
- [ ] 메모리 사용 추이 확인 (시간에 따라 증가하는지)
- [ ] 특정 API 호출 시 메모리 급증하는지 확인

## 디버깅 명령어 모음

```bash
# Pod 상태 확인
kubectl get pods

# OOMKilled 확인
kubectl describe pod <pod-name> | grep -A 10 "Last State"

# 메모리 사용량 확인
kubectl top pod <pod-name>

# 메모리 제한 확인
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].resources}'

# 로그 확인 (OOM 전)
kubectl logs <pod-name> --previous

# 메모리 제한 증가
kubectl set resources deployment <name> --limits=memory=1Gi

# HPA 생성
kubectl autoscale deployment <name> --cpu-percent=70 --min=2 --max=10

# 메모리 사용량 정렬
kubectl top pods --sort-by=memory
```

## 추가 리소스

- [Kubernetes 공식 문서 - Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Linux OOM Killer](https://www.kernel.org/doc/gorman/html/understand/understand016.html)
- [Node.js Memory Management](https://nodejs.org/en/docs/guides/simple-profiling/)

## 요약

OOMKilled는 메모리 제한 초과로 발생합니다. 해결을 위해:

1. **Exit Code 137 확인**: OOMKilled의 명확한 신호
2. **메모리 사용량 확인**: `kubectl top pod`
3. **메모리 제한 증가**: 필요 시 limits 조정
4. **메모리 누수 진단**: 시간에 따라 증가하는지 확인
5. **코드 최적화**: 스트리밍, 캐시 제한, 페이지네이션

대부분의 경우 메모리 제한 부족 또는 메모리 누수가 원인입니다.
