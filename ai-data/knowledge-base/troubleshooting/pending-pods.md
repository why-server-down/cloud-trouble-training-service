# Pending Pods 트러블슈팅 가이드

## 개요

Pod가 `Pending` 상태에 머물러 있다는 것은 Kubernetes 스케줄러가 Pod를 실행할 적절한 Node를 찾지 못했다는 의미입니다. Pod가 생성되었지만 아직 Node에 할당되지 않은 상태입니다.

## 증상

- Pod 상태가 `Pending`으로 표시됨
- `READY` 컬럼이 `0/1`로 표시됨
- Pod가 오랜 시간 동안 시작되지 않음
- 컨테이너가 실행되지 않음

## 원인

### 1. 리소스 부족
- CPU 부족
- 메모리 부족
- 모든 Node가 리소스 한계에 도달

### 2. Node Selector 불일치
- Pod의 nodeSelector가 어떤 Node와도 매치되지 않음
- Node에 필요한 레이블이 없음

### 3. Affinity/Anti-Affinity 규칙
- Node Affinity 조건을 만족하는 Node 없음
- Pod Anti-Affinity로 인한 배치 불가

### 4. Taints and Tolerations
- Node에 Taint가 설정되어 있음
- Pod에 해당 Toleration이 없음

### 5. PersistentVolumeClaim 문제
- PVC가 Bound 상태가 아님
- 사용 가능한 PV가 없음
- StorageClass 문제

### 6. 클러스터 용량 부족
- 모든 Node가 가득 참
- 새 Node 추가 필요

## 진단 방법

### 1. Pod 상태 확인

```bash
kubectl get pods
```

출력 예시:
```
NAME                    READY   STATUS    RESTARTS   AGE
myapp-5d4b7c9f8-xyz12   0/1     Pending   0          5m
```

### 2. Pod 상세 정보 확인

```bash
kubectl describe pod <pod-name>
```

**Events 섹션이 가장 중요**:
```
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  3m    default-scheduler  0/3 nodes are available: 3 Insufficient cpu.
```

일반적인 메시지:
- `Insufficient cpu`: CPU 부족
- `Insufficient memory`: 메모리 부족
- `node(s) didn't match node selector`: nodeSelector 불일치
- `node(s) had taints that the pod didn't tolerate`: Taint/Toleration 문제
- `persistentvolumeclaim "xxx" not found`: PVC 없음

### 3. Node 리소스 확인

```bash
# Node 목록 및 상태
kubectl get nodes

# Node 상세 정보
kubectl describe node <node-name>

# Node 리소스 사용량
kubectl top nodes
```

### 4. PVC 상태 확인

```bash
kubectl get pvc
```

출력 예시:
```
NAME        STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
my-pvc      Pending   -        -          -              standard       5m
```

## 해결 방법

### 1. 리소스 부족 해결

**문제 확인**:
```bash
kubectl describe pod <pod-name>
# Events: 0/3 nodes are available: 3 Insufficient memory.
```

**해결 방법 A: 리소스 요청 줄이기**

```yaml
# 현재 설정
resources:
  requests:
    memory: "2Gi"
    cpu: "1000m"
  limits:
    memory: "4Gi"
    cpu: "2000m"

# 수정 후
resources:
  requests:
    memory: "512Mi"  # 줄임
    cpu: "250m"      # 줄임
  limits:
    memory: "1Gi"
    cpu: "500m"
```

명령어로 수정:
```bash
kubectl set resources deployment <deployment-name> \
  --requests=cpu=250m,memory=512Mi \
  --limits=cpu=500m,memory=1Gi
```

**해결 방법 B: Node 추가**

클러스터에 새 Node 추가 (클라우드 환경):
```bash
# AWS EKS
eksctl scale nodegroup --cluster=my-cluster --name=my-nodegroup --nodes=5

# GKE
gcloud container clusters resize my-cluster --num-nodes=5

# AKS
az aks scale --resource-group myResourceGroup --name myAKSCluster --node-count 5
```

**해결 방법 C: 다른 Pod 제거**

불필요한 Pod 삭제하여 리소스 확보:
```bash
kubectl delete pod <unnecessary-pod>
```

### 2. Node Selector 문제 해결

**문제 확인**:
```bash
kubectl describe pod <pod-name>
# Events: 0/3 nodes are available: 3 node(s) didn't match node selector.
```

Pod의 nodeSelector 확인:
```bash
kubectl get pod <pod-name> -o yaml | grep -A 5 nodeSelector
```

**해결 방법 A: Node에 레이블 추가**

```bash
# Node 레이블 확인
kubectl get nodes --show-labels

# Node에 레이블 추가
kubectl label nodes <node-name> disktype=ssd

# 레이블 확인
kubectl get nodes -l disktype=ssd
```

**해결 방법 B: nodeSelector 제거 또는 수정**

```yaml
# nodeSelector 제거
spec:
  # nodeSelector:
  #   disktype: ssd  # 제거
  containers:
  - name: myapp
    image: myapp:v1
```

또는 올바른 레이블로 수정:
```yaml
spec:
  nodeSelector:
    kubernetes.io/os: linux  # 존재하는 레이블로 변경
```

### 3. Taints and Tolerations 해결

**문제 확인**:
```bash
kubectl describe pod <pod-name>
# Events: 0/3 nodes are available: 3 node(s) had taints that the pod didn't tolerate.
```

Node의 Taint 확인:
```bash
kubectl describe node <node-name> | grep Taints
```

출력 예시:
```
Taints: key=value:NoSchedule
```

**해결 방법 A: Pod에 Toleration 추가**

```yaml
spec:
  tolerations:
  - key: "key"
    operator: "Equal"
    value: "value"
    effect: "NoSchedule"
  containers:
  - name: myapp
    image: myapp:v1
```

**해결 방법 B: Node에서 Taint 제거**

```bash
# Taint 제거
kubectl taint nodes <node-name> key=value:NoSchedule-

# 모든 Taint 제거
kubectl taint nodes <node-name> key-
```

**일반적인 Taint**:
- `node.kubernetes.io/not-ready:NoSchedule`: Node가 준비되지 않음
- `node.kubernetes.io/unreachable:NoSchedule`: Node에 연결할 수 없음
- `node.kubernetes.io/disk-pressure:NoSchedule`: 디스크 공간 부족

### 4. PVC 문제 해결

**문제 확인**:
```bash
kubectl get pvc
# NAME     STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
# my-pvc   Pending   -        -          -              standard       5m
```

**해결 방법 A: PV 생성**

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: my-pv
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: standard
  hostPath:
    path: /mnt/data
```

**해결 방법 B: StorageClass 확인**

```bash
# StorageClass 목록
kubectl get storageclass

# 기본 StorageClass 설정
kubectl patch storageclass <storage-class-name> \
  -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

**해결 방법 C: PVC 수정**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi  # 요청 크기 줄임
  storageClassName: standard  # 존재하는 StorageClass
```

### 5. Affinity 문제 해결

**문제 확인**:
```bash
kubectl describe pod <pod-name>
# Events: 0/3 nodes are available: 3 node(s) didn't match pod affinity rules.
```

**해결 방법: Affinity 규칙 완화**

```yaml
# 엄격한 규칙 (requiredDuringSchedulingIgnoredDuringExecution)
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: disktype
            operator: In
            values:
            - ssd

# 선호 규칙으로 변경 (preferredDuringSchedulingIgnoredDuringExecution)
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 1
        preference:
          matchExpressions:
          - key: disktype
            operator: In
            values:
            - ssd
```

## 실전 예제

### 예제 1: 메모리 부족

**증상**:
```
Events:
  Warning  FailedScheduling  1m  default-scheduler  0/3 nodes are available: 3 Insufficient memory.
```

**해결**:
```bash
# 리소스 요청 줄이기
kubectl set resources deployment myapp \
  --requests=memory=256Mi \
  --limits=memory=512Mi
```

### 예제 2: Node Selector 불일치

**증상**:
```
Events:
  Warning  FailedScheduling  1m  default-scheduler  0/3 nodes are available: 3 node(s) didn't match node selector.
```

**해결**:
```bash
# Node에 레이블 추가
kubectl label nodes node1 environment=production

# 또는 nodeSelector 제거
kubectl patch deployment myapp --type json \
  -p='[{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]'
```

### 예제 3: Taint 문제

**증상**:
```
Events:
  Warning  FailedScheduling  1m  default-scheduler  0/3 nodes are available: 3 node(s) had taints that the pod didn't tolerate.
```

**해결**:
```bash
# Node의 Taint 확인
kubectl describe node node1 | grep Taints

# Taint 제거
kubectl taint nodes node1 key=value:NoSchedule-
```

### 예제 4: PVC Pending

**증상**:
```bash
kubectl get pvc
# NAME     STATUS    VOLUME   CAPACITY
# my-pvc   Pending   -        -
```

**해결**:
```bash
# StorageClass 확인
kubectl get storageclass

# 기본 StorageClass가 없으면 설정
kubectl patch storageclass standard \
  -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

## 예방 방법

### 1. 적절한 리소스 요청 설정

```yaml
resources:
  requests:
    memory: "256Mi"  # 실제 필요한 최소값
    cpu: "100m"
  limits:
    memory: "512Mi"  # 최대값
    cpu: "500m"
```

### 2. 클러스터 오토스케일링 설정

```bash
# GKE
gcloud container clusters update my-cluster \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=10

# EKS (Cluster Autoscaler 설치)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/cluster-autoscaler/cloudprovider/aws/examples/cluster-autoscaler-autodiscover.yaml
```

### 3. Resource Quotas 설정

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute-quota
spec:
  hard:
    requests.cpu: "10"
    requests.memory: "20Gi"
    limits.cpu: "20"
    limits.memory: "40Gi"
```

### 4. PriorityClass 사용

중요한 Pod에 우선순위 부여:
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority
value: 1000
globalDefault: false
---
apiVersion: v1
kind: Pod
metadata:
  name: important-pod
spec:
  priorityClassName: high-priority
  containers:
  - name: myapp
    image: myapp:v1
```

## 체크리스트

진단 시 확인할 사항:

- [ ] `kubectl describe pod`로 Events 확인
- [ ] Node 리소스 사용량 확인 (`kubectl top nodes`)
- [ ] Pod 리소스 요청 확인
- [ ] nodeSelector 설정 확인
- [ ] Node 레이블 확인 (`kubectl get nodes --show-labels`)
- [ ] Node Taints 확인 (`kubectl describe node`)
- [ ] PVC 상태 확인 (`kubectl get pvc`)
- [ ] StorageClass 확인 (`kubectl get storageclass`)
- [ ] Affinity/Anti-Affinity 규칙 확인

## 디버깅 명령어 모음

```bash
# Pod 상태 확인
kubectl get pods -o wide

# Pod 상세 정보 (Events 포함)
kubectl describe pod <pod-name>

# Node 리소스 확인
kubectl top nodes
kubectl describe nodes

# Node 레이블 확인
kubectl get nodes --show-labels

# PVC 상태 확인
kubectl get pvc

# StorageClass 확인
kubectl get storageclass

# 리소스 요청 수정
kubectl set resources deployment <name> --requests=cpu=100m,memory=256Mi

# Node 레이블 추가
kubectl label nodes <node-name> key=value

# Taint 제거
kubectl taint nodes <node-name> key=value:NoSchedule-
```

## 추가 리소스

- [Kubernetes 공식 문서 - Scheduling](https://kubernetes.io/docs/concepts/scheduling-eviction/)
- [Kubernetes 공식 문서 - Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
- [Kubernetes 공식 문서 - Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)

## 요약

Pending Pod는 스케줄러가 적절한 Node를 찾지 못했을 때 발생합니다. 해결을 위해:

1. **Events 확인**: `kubectl describe pod`로 정확한 원인 파악
2. **리소스 확인**: CPU/메모리 부족 여부
3. **Node Selector**: 레이블 일치 여부
4. **Taints**: Node Taint와 Pod Toleration 확인
5. **PVC**: PersistentVolumeClaim 상태 확인

대부분의 경우 리소스 부족 또는 Node Selector 불일치가 원인입니다.
