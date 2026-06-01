# ImagePullBackOff 트러블슈팅 가이드

## 개요

ImagePullBackOff는 Kubernetes가 컨테이너 이미지를 레지스트리에서 가져오는 데 실패했을 때 발생하는 오류입니다. Pod가 시작되지 않고 이미지를 가져오려는 시도를 반복합니다.

## 증상

- Pod 상태가 `ImagePullBackOff` 또는 `ErrImagePull`로 표시됨
- Pod가 `Pending` 상태에서 멈춤
- 컨테이너가 시작되지 않음
- Events에 이미지 pull 실패 메시지

## 원인

### 1. 이미지 이름 오류
- 오타 (예: `ngnix` 대신 `nginx`)
- 잘못된 태그 (예: 존재하지 않는 버전)
- 잘못된 레지스트리 URL

### 2. 인증 문제
- Private 레지스트리 접근 권한 없음
- imagePullSecrets 누락
- 만료된 인증 정보

### 3. 네트워크 문제
- 레지스트리 서버 다운
- 방화벽 차단
- DNS 해석 실패

### 4. 레지스트리 문제
- 이미지가 삭제됨
- 레지스트리 용량 초과
- 레이트 리밋 초과 (Docker Hub)

## 진단 방법

### 1. Pod 상태 확인

```bash
kubectl get pods
```

출력 예시:
```
NAME                    READY   STATUS             RESTARTS   AGE
myapp-5d4b7c9f8-xyz12   0/1     ImagePullBackOff   0          2m
```

### 2. Pod 상세 정보 확인

```bash
kubectl describe pod <pod-name>
```

**Events 섹션 확인**:
```
Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Normal   Scheduled  2m                 default-scheduler  Successfully assigned default/myapp-xyz to node1
  Normal   Pulling    1m (x4 over 2m)    kubelet            Pulling image "myapp:v1.0.0"
  Warning  Failed     1m (x4 over 2m)    kubelet            Failed to pull image "myapp:v1.0.0": rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/library/myapp:v1.0.0": failed to resolve reference "docker.io/library/myapp:v1.0.0": docker.io/library/myapp:v1.0.0: not found
  Warning  Failed     1m (x4 over 2m)    kubelet            Error: ErrImagePull
  Normal   BackOff    1m (x6 over 2m)    kubelet            Back-off pulling image "myapp:v1.0.0"
  Warning  Failed     1m (x6 over 2m)    kubelet            Error: ImagePullBackOff
```

### 3. 이미지 정보 확인

Deployment/Pod YAML에서 이미지 확인:
```bash
kubectl get deployment <deployment-name> -o yaml | grep image:
```

또는:
```bash
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].image}'
```

### 4. imagePullSecrets 확인

```bash
kubectl get pod <pod-name> -o yaml | grep -A 5 imagePullSecrets
```

## 해결 방법

### 1. 이미지 이름 확인 및 수정

**문제**: 오타 또는 잘못된 이미지 이름

**확인**:
```bash
# 이미지가 레지스트리에 존재하는지 확인
docker pull <image-name>:<tag>
```

**해결**:
```yaml
# Deployment 수정
spec:
  containers:
  - name: myapp
    image: nginx:1.21  # 올바른 이름과 태그
```

또는 명령어로 수정:
```bash
kubectl set image deployment/<deployment-name> <container-name>=<correct-image>
```

**일반적인 오타**:
- `ngnix` → `nginx`
- `redis:lastest` → `redis:latest`
- `postgres:13` → `postgres:13.0` (태그 확인)

### 2. Private 레지스트리 인증 설정

**문제**: Private 레지스트리 접근 권한 없음

**해결 - Docker Hub**:

1. Secret 생성:
```bash
kubectl create secret docker-registry regcred \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username=<your-username> \
  --docker-password=<your-password> \
  --docker-email=<your-email>
```

2. Pod에 Secret 추가:
```yaml
spec:
  imagePullSecrets:
  - name: regcred
  containers:
  - name: myapp
    image: <your-username>/myapp:v1.0.0
```

**해결 - AWS ECR**:

1. ECR 로그인 토큰 생성:
```bash
aws ecr get-login-password --region us-east-1 | \
  kubectl create secret docker-registry ecr-secret \
  --docker-server=<account-id>.dkr.ecr.us-east-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password-stdin
```

2. Pod에 Secret 추가:
```yaml
spec:
  imagePullSecrets:
  - name: ecr-secret
  containers:
  - name: myapp
    image: <account-id>.dkr.ecr.us-east-1.amazonaws.com/myapp:v1.0.0
```

**해결 - Google GCR**:

1. Service Account Key 다운로드
2. Secret 생성:
```bash
kubectl create secret docker-registry gcr-secret \
  --docker-server=gcr.io \
  --docker-username=_json_key \
  --docker-password="$(cat key.json)" \
  --docker-email=<your-email>
```

**해결 - Harbor/Private Registry**:

```bash
kubectl create secret docker-registry harbor-secret \
  --docker-server=harbor.example.com \
  --docker-username=<username> \
  --docker-password=<password>
```

### 3. 네트워크 문제 해결

**DNS 확인**:
```bash
# Node에서 DNS 테스트
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup docker.io
```

**레지스트리 연결 확인**:
```bash
# Node에서 레지스트리 연결 테스트
kubectl run -it --rm debug --image=busybox --restart=Never -- wget -O- https://index.docker.io/v1/
```

**프록시 설정** (필요한 경우):
```yaml
env:
- name: HTTP_PROXY
  value: "http://proxy.example.com:8080"
- name: HTTPS_PROXY
  value: "http://proxy.example.com:8080"
- name: NO_PROXY
  value: "localhost,127.0.0.1,.cluster.local"
```

### 4. 이미지 Pull Policy 조정

**문제**: 로컬에 이미지가 있지만 계속 pull 시도

**해결**:
```yaml
spec:
  containers:
  - name: myapp
    image: myapp:latest
    imagePullPolicy: IfNotPresent  # 또는 Never
```

**imagePullPolicy 옵션**:
- `Always`: 항상 pull (기본값, tag가 `:latest`인 경우)
- `IfNotPresent`: 로컬에 없으면 pull
- `Never`: 로컬 이미지만 사용

### 5. Docker Hub Rate Limit 해결

**문제**: Docker Hub 무료 계정 rate limit 초과

**증상**:
```
Error: toomanyrequests: You have reached your pull rate limit
```

**해결 방법**:

1. **Docker Hub 로그인** (인증된 사용자는 더 높은 limit):
```bash
kubectl create secret docker-registry dockerhub \
  --docker-username=<username> \
  --docker-password=<password>
```

2. **이미지 캐싱**: 자체 레지스트리에 이미지 미러링

3. **대체 레지스트리 사용**:
```yaml
image: quay.io/nginx/nginx:1.21  # Quay.io 사용
```

## 실전 예제

### 예제 1: 이미지 이름 오타

**증상**:
```
Failed to pull image "ngnix:latest": rpc error: code = NotFound
```

**해결**:
```bash
# Deployment 수정
kubectl set image deployment/myapp myapp=nginx:latest

# 또는 YAML 수정
kubectl edit deployment myapp
# image: ngnix:latest → nginx:latest
```

### 예제 2: Private 레지스트리 인증 누락

**증상**:
```
Failed to pull image "myregistry.com/myapp:v1": unauthorized
```

**해결**:
```bash
# 1. Secret 생성
kubectl create secret docker-registry my-registry-secret \
  --docker-server=myregistry.com \
  --docker-username=myuser \
  --docker-password=mypass

# 2. Deployment에 추가
kubectl patch deployment myapp -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"my-registry-secret"}]}}}}'
```

### 예제 3: 존재하지 않는 태그

**증상**:
```
Failed to pull image "nginx:1.99": manifest unknown
```

**해결**:
```bash
# 사용 가능한 태그 확인
docker search nginx --limit 5

# 올바른 태그로 수정
kubectl set image deployment/myapp myapp=nginx:1.21
```

### 예제 4: AWS ECR 인증

**증상**:
```
Failed to pull image "123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:v1": no basic auth credentials
```

**해결**:
```bash
# 1. ECR 로그인 토큰 생성 및 Secret 생성
aws ecr get-login-password --region us-east-1 | \
  kubectl create secret docker-registry ecr-secret \
  --docker-server=123456789.dkr.ecr.us-east-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password-stdin

# 2. Deployment에 추가
kubectl patch deployment myapp -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"ecr-secret"}]}}}}'
```

## 예방 방법

### 1. 이미지 이름 검증

배포 전 이미지 존재 여부 확인:
```bash
docker pull <image-name>:<tag>
```

### 2. imagePullSecrets 자동 추가

ServiceAccount에 imagePullSecrets 설정:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: default
imagePullSecrets:
- name: regcred
```

### 3. 이미지 태그 명시

`:latest` 태그 사용 지양:
```yaml
# 나쁜 예
image: myapp:latest

# 좋은 예
image: myapp:v1.2.3
```

### 4. 로컬 레지스트리 사용

자주 사용하는 이미지는 클러스터 내부 레지스트리에 캐싱

### 5. CI/CD 파이프라인 검증

배포 전 이미지 pull 테스트:
```bash
# CI/CD 스크립트에 추가
docker pull $IMAGE_NAME:$IMAGE_TAG || exit 1
```

## 체크리스트

진단 시 확인할 사항:

- [ ] `kubectl describe pod`로 정확한 에러 메시지 확인
- [ ] 이미지 이름과 태그 오타 확인
- [ ] 이미지가 레지스트리에 존재하는지 확인
- [ ] Private 레지스트리인 경우 imagePullSecrets 설정 확인
- [ ] Secret이 올바른 namespace에 있는지 확인
- [ ] 네트워크 연결 확인 (DNS, 방화벽)
- [ ] Docker Hub rate limit 확인
- [ ] imagePullPolicy 설정 확인

## 디버깅 명령어 모음

```bash
# Pod 상태 확인
kubectl get pods

# 상세 정보 및 Events 확인
kubectl describe pod <pod-name>

# 이미지 정보 확인
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].image}'

# imagePullSecrets 확인
kubectl get pod <pod-name> -o yaml | grep -A 5 imagePullSecrets

# Secret 목록 확인
kubectl get secrets

# Secret 상세 정보
kubectl describe secret <secret-name>

# Node에서 이미지 pull 테스트
kubectl debug node/<node-name> -it --image=busybox

# Deployment 이미지 변경
kubectl set image deployment/<name> <container>=<new-image>

# Deployment 재시작
kubectl rollout restart deployment/<name>
```

## 추가 리소스

- [Kubernetes 공식 문서 - Images](https://kubernetes.io/docs/concepts/containers/images/)
- [Kubernetes 공식 문서 - Pull an Image from a Private Registry](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)
- [Docker Hub Rate Limits](https://docs.docker.com/docker-hub/download-rate-limit/)

## 요약

ImagePullBackOff는 이미지를 가져오는 데 실패했을 때 발생합니다. 해결을 위해:

1. **이미지 이름 확인**: 오타, 태그, 레지스트리 URL
2. **인증 확인**: imagePullSecrets 설정 (Private 레지스트리)
3. **네트워크 확인**: DNS, 방화벽, 레지스트리 연결
4. **Rate Limit 확인**: Docker Hub 무료 계정 제한
5. **Events 확인**: `kubectl describe pod`로 정확한 에러 메시지 확인

대부분의 경우 이미지 이름 오타 또는 인증 문제입니다.
