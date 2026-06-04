# Service 설정 오류 (Service Selector Mismatch) 트러블슈팅 가이드

## 개요

Kubernetes Service의 `selector`가 Pod의 실제 레이블과 일치하지 않으면 Service에 Endpoint가 연결되지 않아 트래픽이 Pod에 도달하지 못합니다. Pod는 정상적으로 Running 상태이지만 서비스를 통한 접근이 불가능합니다.

## 증상

- Pod 상태는 `Running`이지만 서비스 응답 없음
- `kubectl get endpoints webapp-svc` 결과에 Endpoint가 없음 (`<none>`)
- `curl` 또는 포트포워딩으로 접속 시 연결 실패
- `kubectl describe svc webapp-svc`의 `Endpoints` 항목이 비어있음

## 원인

Service의 `spec.selector`가 Pod의 `metadata.labels`와 다른 경우 발생합니다.

예시:
- Pod 레이블: `app: webapp`
- Service selector: `app: webapp-broken` ← 불일치

Service는 selector와 **완전히 일치**하는 레이블을 가진 Pod를 대상으로 Endpoint를 생성합니다. 하나라도 다르면 Endpoint가 비어있게 됩니다.

## 진단 방법

### 1. Pod 상태 및 레이블 확인

```bash
kubectl get pods --show-labels
```

출력 예시:
```
NAME                      READY   STATUS    RESTARTS   AGE   LABELS
webapp-7d8f9c-abc12       1/1     Running   0          2m    app=webapp
```

### 2. Service Endpoint 확인

```bash
kubectl get endpoints webapp-svc
```

정상: `ENDPOINTS` 칼럼에 Pod IP가 표시됨
비정상: `<none>` 또는 아무것도 없음

```bash
kubectl describe svc webapp-svc
```

주요 확인 사항:
- **Selector**: Service가 어떤 레이블을 찾고 있는지
- **Endpoints**: 연결된 Pod IP 목록

### 3. Service selector와 Pod 레이블 비교

```bash
# Service의 selector 확인
kubectl get svc webapp-svc -o jsonpath='{.spec.selector}'

# selector와 동일한 레이블을 가진 Pod 조회
kubectl get pods -l app=webapp
```

selector가 `app=webapp-broken`이라면:
```bash
kubectl get pods -l app=webapp-broken
# 결과: No resources found → Endpoint 없는 이유 확인됨
```

## 해결 방법

### Service selector 수정 (kubectl patch)

```bash
kubectl patch svc webapp-svc -p '{"spec":{"selector":{"app":"webapp"}}}'
```

### Service selector 수정 (kubectl edit)

```bash
kubectl edit svc webapp-svc
```

편집기에서 `spec.selector` 부분을 수정:

```yaml
spec:
  selector:
    app: webapp   # webapp-broken → webapp 으로 수정
```

## 수정 후 확인

```bash
# Endpoint가 생성되었는지 확인
kubectl get endpoints webapp-svc

# 정상 출력 예시:
# NAME         ENDPOINTS         AGE
# webapp-svc   10.244.0.5:80     1s
```

Endpoint에 Pod IP가 표시되면 서비스가 정상적으로 Pod와 연결된 것입니다.

## 핵심 개념

| 개념 | 설명 |
|------|------|
| Service selector | Service가 트래픽을 전달할 Pod를 찾는 레이블 조건 |
| Pod label | Pod에 붙은 키-값 식별자 |
| Endpoint | selector와 일치하는 Pod의 IP:Port 목록 |
| Endpoint 없음 | selector 불일치, 또는 해당 레이블의 Running Pod가 없음 |

## 관련 kubectl 명령어

```bash
# 모든 Service 확인
kubectl get svc

# Service 상세 정보 (selector, endpoints, port 포함)
kubectl describe svc <service-name>

# Endpoint 목록
kubectl get endpoints

# 특정 레이블 Pod 조회
kubectl get pods -l <key>=<value>

# Service selector 확인 (JSON)
kubectl get svc <service-name> -o jsonpath='{.spec.selector}'

# Service 설정 변경 (patch)
kubectl patch svc <service-name> -p '{"spec":{"selector":{"<key>":"<value>"}}}'
```
