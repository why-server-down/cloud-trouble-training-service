# Chaos Mission System - Requirements

## Overview
Chaos Mesh를 활용하여 실제와 동일한 장애 상황을 안전하게 연출하고, 사용자가 단계별 미션을 해결하도록 하는 게이미피케이션 기반 장애 대응 훈련 시스템입니다.

## User Stories

### 1. Mission Initialization (미션 초기화)
**As a** 학습자  
**I want** 미션을 시작하면 자동으로 K8s 환경이 구성되기를  
**So that** 복잡한 설정 없이 바로 학습을 시작할 수 있다

**Acceptance Criteria:**
- 1.1 사용자가 미션을 선택하면 해당 미션의 K8s 리소스가 자동 배포된다
- 1.2 미션별 네임스페이스가 생성되어 격리된 환경을 제공한다
- 1.3 초기 상태는 정상 작동하는 애플리케이션이다
- 1.4 미션 초기화는 30초 이내에 완료되어야 한다
- 1.5 초기화 실패 시 명확한 에러 메시지를 제공한다

### 2. Chaos Injection (장애 주입)
**As a** 시스템  
**I want** 미션 시작 후 자동으로 장애를 주입하기를  
**So that** 사용자가 실전과 같은 장애 상황을 경험할 수 있다

**Acceptance Criteria:**
- 2.1 미션 시작 10초 후 Chaos Mesh를 통해 장애가 주입된다
- 2.2 장애 유형은 미션 레벨에 따라 다르다 (Pod Failure, Memory Stress, Network Latency, Service Misconfiguration)
- 2.3 장애 주입 성공 여부를 로그로 기록한다
- 2.4 장애는 사용자가 해결할 때까지 지속된다
- 2.5 장애 주입 실패 시 미션을 자동으로 재시작한다

### 3. Mission Validation (미션 검증)
**As a** 학습자  
**I want** 내가 문제를 해결했는지 자동으로 확인되기를  
**So that** 수동으로 채점을 기다리지 않고 즉시 결과를 알 수 있다

**Acceptance Criteria:**
- 3.1 시스템은 5초마다 미션 완료 조건을 자동 체크한다
- 3.2 완료 조건은 미션별로 다르다 (HTTP 200 응답, Pod Running 상태, 응답 시간 등)
- 3.3 조건 충족 시 즉시 성공 알림과 점수를 표시한다
- 3.4 검증 로직은 Prometheus 메트릭을 활용한다
- 3.5 검증 실패 시 현재 상태와 목표 상태를 비교하여 보여준다

### 4. Mission Scenarios (미션 시나리오)
**As a** 학습자  
**I want** 다양한 난이도의 미션을 순차적으로 해결하기를  
**So that** 단계적으로 실력을 향상시킬 수 있다

**Acceptance Criteria:**
- 4.1 Level 1: Pod Failure (ImagePullBackOff) - 이미지 이름 오타 수정
- 4.2 Level 2: Memory Stress (OOMKilled) - 메모리 리소스 제한 조정
- 4.3 Level 3: Service Misconfiguration - Selector와 Label 불일치 수정
- 4.4 Level 4: Network Latency - Liveness Probe 설정으로 자동 복구
- 4.5 각 미션은 이전 미션 완료 후에만 잠금 해제된다

### 5. Time-based Scoring (시간 기반 점수)
**As a** 학습자  
**I want** 빠르게 해결할수록 높은 점수를 받기를  
**So that** 효율적인 문제 해결 능력을 기를 수 있다

**Acceptance Criteria:**
- 5.1 미션 시작 시 기본 점수 100점에서 시작한다
- 5.2 1분마다 2점씩 차감된다 (최소 20점 보장)
- 5.3 힌트 사용 시 추가 차감된다 (1단계: -5점, 2단계: -10점, 3단계: -50점)
- 5.4 최종 점수는 데이터베이스에 저장되어 리더보드에 반영된다
- 5.5 미션 포기 시 0점 처리된다

## Technical Requirements

### Infrastructure
- Kubernetes 클러스터 (Minikube 또는 EKS)
- Chaos Mesh 설치 및 구성
- 미션별 네임스페이스 격리
- 리소스 쿼터 설정으로 과도한 리소스 사용 방지

### Monitoring
- Prometheus로 파드 상태 모니터링
- 미션 완료 조건을 메트릭으로 정의
- 장애 주입 전후 상태 비교

### Performance
- 미션 초기화: 30초 이내
- 장애 주입: 10초 이내
- 검증 주기: 5초
- 동시 미션 실행: 사용자당 1개
