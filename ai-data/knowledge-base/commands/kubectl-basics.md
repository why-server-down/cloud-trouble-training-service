# kubectl 기본 명령어 가이드

## 개요

kubectl은 Kubernetes 클러스터와 상호작용하기 위한 커맨드라인 도구입니다. 이 가이드는 가장 자주 사용되는 기본 명령어들을 다룹니다.

## 기본 문법

```bash
kubectl [command] [TYPE] [NAME] [flags]
```

- **command**: 수행할 작업 (get, describe, create, delete 등)
- **TYPE**: 리소스 타입 (pod, service, deployment 등)
- **NAME**: 리소스 이름 (선택사항)
- **flags**: 추가 옵션 (선택사항)

## 클러스터 정보

### 클러스터 상태 확인

```bash
# 클러스터 정보
kubectl cluster-info

# 클러스터 버전
kubectl version

# 클러스터 상태
kubectl get componentstatuses
```

### Context 관리

```bash
# 현재 context 확인
kubectl config current-context

# 사용 가능한 context 목록
kubectl config get-contexts

# context 전환
kubectl config use-context <context-name>

# context 설정 보기
kubectl config view
```

## Pod 관리

### Pod 조회

```bash
# 모든 Pod 조회
kubectl get pods

# 모든 namespace의 Pod 조회
kubectl get pods --all-namespaces
kubectl get pods -A

# 특정 namespace의 Pod 조회
kubectl get pods -n <namespace>

# 상세 정보 포함
kubectl get pods -o wide

# YAML 형식으로 출력
kubectl get pod <pod-name> -o yaml

# JSON 형식으로 출력
kubectl get pod <pod-name> -o json

# 특정 필드만 출력
kubectl get pods -o custom-columns=NAME:.metadata.name,STATUS:.status.phase

# 레이블과 함께 출력
kubectl get pods --show-labels

# 레이블로 필터링
kubectl get pods -l app=myapp
kubectl get pods -l 'environment in (production,staging)'
```

### Pod 생성

```bash
# YAML 파일로 생성
kubectl apply -f pod.yaml

# 간단한 Pod 생성 (테스트용)
kubectl run nginx --image=nginx

# 환경 변수와 함께 생성
kubectl run myapp --image=myapp:v1 --env="ENV=production"

# 포트 노출
kubectl run nginx --image=nginx --port=80

# Dry-run (실제 생성하지 않고 YAML 생성)
kubectl run nginx --image=nginx --dry-run=client -o yaml > pod.yaml
```

### Pod 삭제

```bash
# Pod 삭제
kubectl delete pod <pod-name>

# 여러 Pod 삭제
kubectl delete pod <pod1> <pod2> <pod3>

# 레이블로 삭제
kubectl delete pods -l app=myapp

# YAML 파일로 삭제
kubectl delete -f pod.yaml

# 강제 삭제 (즉시 삭제)
kubectl delete pod <pod-name> --force --grace-period=0

# namespace의 모든 Pod 삭제
kubectl delete pods --all -n <namespace>
```

## Deployment 관리

### Deployment 조회

```bash
# Deployment 목록
kubectl get deployments

# 상세 정보
kubectl get deployment <deployment-name> -o wide

# Deployment 상태 확인
kubectl rollout status deployment/<deployment-name>

# Deployment 히스토리
kubectl rollout history deployment/<deployment-name>
```

### Deployment 생성

```bash
# 이미지로 Deployment 생성
kubectl create deployment nginx --image=nginx

# 레플리카 수 지정
kubectl create deployment nginx --image=nginx --replicas=3

# Dry-run으로 YAML 생성
kubectl create deployment nginx --image=nginx --dry-run=client -o yaml > deployment.yaml

# YAML 파일로 생성
kubectl apply -f deployment.yaml
```

### Deployment 업데이트

```bash
# 이미지 업데이트
kubectl set image deployment/<deployment-name> <container-name>=<new-image>

# 예시
kubectl set image deployment/nginx nginx=nginx:1.21

# 리소스 업데이트
kubectl set resources deployment/<deployment-name> \
  --limits=cpu=200m,memory=512Mi \
  --requests=cpu=100m,memory=256Mi

# 환경 변수 업데이트
kubectl set env deployment/<deployment-name> ENV=production

# YAML 파일 수정 후 적용
kubectl apply -f deployment.yaml

# 직접 편집
kubectl edit deployment/<deployment-name>
```

### Deployment 스케일링

```bash
# 레플리카 수 변경
kubectl scale deployment/<deployment-name> --replicas=5

# 조건부 스케일링
kubectl scale deployment/<deployment-name> --current-replicas=2 --replicas=3

# 오토스케일링 설정
kubectl autoscale deployment/<deployment-name> --min=2 --max=10 --cpu-percent=80
```

### Deployment 롤백

```bash
# 이전 버전으로 롤백
kubectl rollout undo deployment/<deployment-name>

# 특정 리비전으로 롤백
kubectl rollout undo deployment/<deployment-name> --to-revision=2

# 롤아웃 일시 중지
kubectl rollout pause deployment/<deployment-name>

# 롤아웃 재개
kubectl rollout resume deployment/<deployment-name>

# 롤아웃 재시작
kubectl rollout restart deployment/<deployment-name>
```

## Service 관리

### Service 조회

```bash
# Service 목록
kubectl get services
kubectl get svc

# 상세 정보
kubectl get svc <service-name> -o wide

# Endpoints 확인
kubectl get endpoints <service-name>
```

### Service 생성

```bash
# Deployment를 Service로 노출
kubectl expose deployment/<deployment-name> --port=80 --target-port=8080

# NodePort로 노출
kubectl expose deployment/<deployment-name> --type=NodePort --port=80

# LoadBalancer로 노출
kubectl expose deployment/<deployment-name> --type=LoadBalancer --port=80

# YAML 파일로 생성
kubectl apply -f service.yaml
```

### Service 삭제

```bash
# Service 삭제
kubectl delete service <service-name>

# YAML 파일로 삭제
kubectl delete -f service.yaml
```

## Namespace 관리

### Namespace 조회

```bash
# Namespace 목록
kubectl get namespaces
kubectl get ns

# 현재 namespace 확인
kubectl config view --minify | grep namespace:
```

### Namespace 생성

```bash
# Namespace 생성
kubectl create namespace <namespace-name>

# YAML 파일로 생성
kubectl apply -f namespace.yaml
```

### Namespace 전환

```bash
# 기본 namespace 변경
kubectl config set-context --current --namespace=<namespace-name>

# 특정 명령어에만 namespace 지정
kubectl get pods -n <namespace-name>
```

### Namespace 삭제

```bash
# Namespace 삭제 (내부의 모든 리소스도 삭제됨)
kubectl delete namespace <namespace-name>
```

## ConfigMap & Secret

### ConfigMap

```bash
# ConfigMap 조회
kubectl get configmaps
kubectl get cm

# ConfigMap 생성 (리터럴)
kubectl create configmap <name> --from-literal=key1=value1 --from-literal=key2=value2

# ConfigMap 생성 (파일)
kubectl create configmap <name> --from-file=config.txt

# ConfigMap 생성 (디렉토리)
kubectl create configmap <name> --from-file=config-dir/

# ConfigMap 내용 확인
kubectl get configmap <name> -o yaml

# ConfigMap 삭제
kubectl delete configmap <name>
```

### Secret

```bash
# Secret 조회
kubectl get secrets

# Secret 생성 (리터럴)
kubectl create secret generic <name> --from-literal=password=mypassword

# Secret 생성 (파일)
kubectl create secret generic <name> --from-file=ssh-privatekey=~/.ssh/id_rsa

# Docker registry Secret
kubectl create secret docker-registry <name> \
  --docker-server=<server> \
  --docker-username=<username> \
  --docker-password=<password>

# Secret 내용 확인 (base64 인코딩됨)
kubectl get secret <name> -o yaml

# Secret 디코딩
kubectl get secret <name> -o jsonpath='{.data.password}' | base64 --decode

# Secret 삭제
kubectl delete secret <name>
```

## 리소스 정보 조회

### 상세 정보

```bash
# Pod 상세 정보 (Events 포함)
kubectl describe pod <pod-name>

# Deployment 상세 정보
kubectl describe deployment <deployment-name>

# Node 상세 정보
kubectl describe node <node-name>

# Service 상세 정보
kubectl describe service <service-name>
```

### 여러 리소스 조회

```bash
# 모든 리소스 조회
kubectl get all

# 특정 namespace의 모든 리소스
kubectl get all -n <namespace>

# 여러 타입의 리소스 조회
kubectl get pods,services,deployments
```

### 리소스 감시

```bash
# Pod 상태 실시간 감시
kubectl get pods --watch
kubectl get pods -w

# 특정 Pod 감시
kubectl get pod <pod-name> --watch
```

## 레이블 및 어노테이션

### 레이블 관리

```bash
# 레이블 추가
kubectl label pod <pod-name> environment=production

# 레이블 수정 (덮어쓰기)
kubectl label pod <pod-name> environment=staging --overwrite

# 레이블 제거
kubectl label pod <pod-name> environment-

# 레이블로 조회
kubectl get pods -l environment=production
kubectl get pods -l 'environment in (production,staging)'
kubectl get pods -l environment!=production
```

### 어노테이션 관리

```bash
# 어노테이션 추가
kubectl annotate pod <pod-name> description="My application"

# 어노테이션 수정
kubectl annotate pod <pod-name> description="Updated description" --overwrite

# 어노테이션 제거
kubectl annotate pod <pod-name> description-
```

## 유용한 팁

### 출력 형식

```bash
# Wide 출력 (더 많은 정보)
kubectl get pods -o wide

# YAML 형식
kubectl get pod <pod-name> -o yaml

# JSON 형식
kubectl get pod <pod-name> -o json

# JSONPath (특정 필드만)
kubectl get pods -o jsonpath='{.items[*].metadata.name}'

# Custom columns
kubectl get pods -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,IP:.status.podIP

# 정렬
kubectl get pods --sort-by=.metadata.creationTimestamp
kubectl get pods --sort-by=.status.startTime
```

### 별칭 (Alias)

```bash
# ~/.bashrc 또는 ~/.zshrc에 추가
alias k='kubectl'
alias kgp='kubectl get pods'
alias kgs='kubectl get services'
alias kgd='kubectl get deployments'
alias kdp='kubectl describe pod'
alias kl='kubectl logs'
alias kex='kubectl exec -it'

# 사용 예시
k get pods
kgp -n production
kdp my-pod
```

### 자동 완성

```bash
# Bash
source <(kubectl completion bash)
echo "source <(kubectl completion bash)" >> ~/.bashrc

# Zsh
source <(kubectl completion zsh)
echo "source <(kubectl completion zsh)" >> ~/.zshrc

# 별칭에도 자동 완성 적용
complete -F __start_kubectl k
```

## 자주 사용하는 명령어 조합

```bash
# 모든 namespace의 Pod 상태 확인
kubectl get pods -A -o wide

# 특정 레이블의 Pod 삭제
kubectl delete pods -l app=myapp

# 모든 Deployment 재시작
kubectl rollout restart deployment --all

# 리소스 사용량 확인
kubectl top nodes
kubectl top pods

# 특정 컨테이너의 로그
kubectl logs <pod-name> -c <container-name>

# 이전 컨테이너 로그 (크래시 후)
kubectl logs <pod-name> --previous

# Pod 내부 명령 실행
kubectl exec <pod-name> -- ls /app

# Pod 내부 쉘 접속
kubectl exec -it <pod-name> -- /bin/bash

# 파일 복사 (로컬 → Pod)
kubectl cp local-file.txt <pod-name>:/path/in/pod

# 파일 복사 (Pod → 로컬)
kubectl cp <pod-name>:/path/in/pod/file.txt local-file.txt

# 포트 포워딩
kubectl port-forward <pod-name> 8080:80

# Service 포트 포워딩
kubectl port-forward service/<service-name> 8080:80
```

## 디버깅 명령어

```bash
# Pod 이벤트 확인
kubectl get events --sort-by=.metadata.creationTimestamp

# 특정 Pod 이벤트
kubectl get events --field-selector involvedObject.name=<pod-name>

# 리소스 사용량
kubectl top pod <pod-name>
kubectl top node <node-name>

# API 리소스 목록
kubectl api-resources

# API 버전 목록
kubectl api-versions

# 클러스터 진단
kubectl get componentstatuses
```

## 추가 리소스

- [kubectl 공식 문서](https://kubernetes.io/docs/reference/kubectl/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [kubectl 명령어 참조](https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands)

## 요약

kubectl 기본 명령어:

- **조회**: `kubectl get <resource>`
- **상세 정보**: `kubectl describe <resource> <name>`
- **생성**: `kubectl create/apply -f <file>`
- **삭제**: `kubectl delete <resource> <name>`
- **업데이트**: `kubectl set/edit <resource> <name>`
- **스케일링**: `kubectl scale deployment/<name> --replicas=<n>`
- **로그**: `kubectl logs <pod-name>`
- **실행**: `kubectl exec -it <pod-name> -- <command>`

가장 자주 사용하는 명령어를 별칭으로 설정하면 생산성이 크게 향상됩니다.
