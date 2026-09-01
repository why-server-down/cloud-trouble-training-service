"""
AI 시나리오 생성 에이전트.
- mock 모드: 난이도별 fixture JSON 반환 (OpenAI 없이 동작)
- openai/gemini 모드: scenario_gen.md 시스템 프롬프트 기반 실제 생성
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class ScenarioGenerationInput:
    difficulty: str  # beginner | intermediate | advanced | expert
    namespace: str
    recent_fault_types: list[str]
    allowed_fault_types: list[str]
    environment: str = "kubernetes"


@dataclass
class ScenarioCandidate:
    scenario: dict
    score: float
    rejected: bool = False
    rejection_reason: str | None = None


# 난이도별 Mock Fixture 시나리오
# nginx Deployment는 k8s_setup.py가 항상 생성하므로 타겟으로 사용
# service_misconfig 시나리오는 webapp/webapp-svc를 사용 (기존 static mission 3과 동일 자원)
_MOCK_FIXTURES: dict[str, list[dict]] = {
    "beginner": [
        {
            "title": "서버가 계속 재시작됩니다",
            "difficulty": "beginner",
            "learning_objectives": [
                "CrashLoopBackOff 상태의 의미와 원인을 설명할 수 있다",
                "kubectl describe와 logs로 컨테이너 종료 원인을 파악할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 시작되자마자 계속 재시작되고 있습니다. "
                "Pod 상태를 확인하고 원인을 찾아 정상화하세요."
            ),
            "internal_summary": "nginx 컨테이너 command가 'exit 1'로 설정되어 즉시 종료 → CrashLoopBackOff",
            "fault": {
                "type": "crash_loop",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "nginx Deployment에서 잘못된 command 설정을 제거한다",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod CrashLoopBackOff 상태", "restart count 계속 증가", "logs에서 즉시 종료 확인"],
                "suggested_queries": [],
                "log_signals": ["exit code 1", "Back-off restarting failed container"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_healthy",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 10,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 80, "hint_penalty": 5, "time_limit_seconds": 900},
        },
        {
            "title": "웹서버가 시작되지 않습니다",
            "difficulty": "beginner",
            "learning_objectives": [
                "ImagePullBackOff 상태의 의미를 설명할 수 있다",
                "잘못된 이미지 태그를 kubectl로 수정할 수 있다",
            ],
            "student_brief": (
                "nginx 배포 후 Pod이 Running 상태가 되지 않습니다. "
                "클러스터의 Pod 상태를 확인하고 원인을 찾아 정상화하세요."
            ),
            "internal_summary": "nginx:wrongtag 이미지 태그로 인한 ImagePullBackOff 장애",
            "fault": {
                "type": "image_pull_error",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"wrong_image": "nginx:wrongtag", "original_image": "nginx:latest"},
            },
            "expected_solution": {
                "summary": "nginx Deployment 이미지를 nginx:latest로 수정한다",
                "allowed_fix_patterns": [
                    "kubectl set image deployment/nginx nginx=nginx:latest",
                    "kubectl edit deployment nginx",
                    "kubectl patch deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod이 ImagePullBackOff 상태", "Events에 이미지 풀 실패 메시지"],
                "suggested_queries": [],
                "log_signals": ["failed to pull image", "ErrImagePull"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_healthy",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 10,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 80, "hint_penalty": 5, "time_limit_seconds": 900},
        },
        {
            "title": "레지스트리 인증 오류",
            "difficulty": "beginner",
            "learning_objectives": [
                "ImagePullBackOff의 원인이 태그 오류와 인증 오류로 다름을 구분할 수 있다",
                "kubectl describe Events에서 pull 실패 원인을 읽을 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 실행되지 않고 있습니다. "
                "이미지를 가져오는 과정에서 오류가 발생한 것 같습니다. "
                "정확한 원인을 확인하고 Pod를 정상화하세요."
            ),
            "internal_summary": "nginx 이미지가 접근 불가한 private registry(private.registry.internal)로 설정되어 unauthorized ImagePullBackOff 발생",
            "fault": {
                "type": "wrong_image_registry",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"wrong_image": "private.registry.internal/nginx:latest", "original_image": "nginx:latest"},
            },
            "expected_solution": {
                "summary": "nginx Deployment 이미지를 nginx:latest로 수정한다",
                "allowed_fix_patterns": [
                    "kubectl set image deployment/nginx nginx=nginx:latest",
                    "kubectl edit deployment nginx",
                    "kubectl patch deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod ImagePullBackOff 상태", "Events에 unauthorized 또는 connection refused 메시지"],
                "suggested_queries": [],
                "log_signals": ["unauthorized", "connection refused", "ErrImagePull"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_healthy",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 10,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 80, "hint_penalty": 5, "time_limit_seconds": 900},
        },
    ],
    "intermediate": [
        {
            "title": "서비스에 요청이 도달하지 않습니다",
            "difficulty": "intermediate",
            "learning_objectives": [
                "Service selector와 Pod label의 관계를 설명할 수 있다",
                "Endpoints가 비어 있는 상태를 kubectl로 진단할 수 있다",
            ],
            "student_brief": (
                "webapp 서비스가 배포되었지만 요청이 Pod에 도달하지 않습니다. "
                "서비스와 Pod 간 연결을 확인하고 정상화하세요."
            ),
            "internal_summary": "webapp-svc selector가 app=webapp-broken으로 설정되어 Endpoints가 비어 있는 장애",
            "fault": {
                "type": "service_selector_mismatch",
                "target": {"kind": "Service", "name": "webapp-svc", "namespace": "{{namespace}}"},
                "parameters": {
                    "wrong_selector": {"app": "webapp-broken"},
                    "expected_selector": {"app": "webapp"},
                },
            },
            "expected_solution": {
                "summary": "webapp-svc selector를 app=webapp으로 수정한다",
                "allowed_fix_patterns": [
                    "kubectl patch service webapp-svc",
                    "kubectl edit service webapp-svc",
                ],
            },
            "observability": {
                "symptoms": ["Service Endpoints 비어 있음", "Pod는 Running 상태", "서비스 요청 실패"],
                "suggested_queries": [
                    'sum(kube_endpoint_address{namespace="{{namespace}}",endpoint="webapp-svc",ready="true"}) > 0'
                ],
                "log_signals": ["no endpoints available for service"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "webapp_service_has_endpoint",
                        "type": "k8s",
                        "query": "service:webapp-svc:endpoints",
                        "stability_seconds": 15,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 100, "hint_penalty": 7, "time_limit_seconds": 1200},
        },
        {
            "title": "Pod가 스케줄링되지 않습니다",
            "difficulty": "intermediate",
            "learning_objectives": [
                "K8s 스케줄링 과정과 nodeSelector의 역할을 설명할 수 있다",
                "Pending 상태의 원인을 kubectl describe로 진단할 수 있다",
            ],
            "student_brief": (
                "nginx Deployment를 배포했는데 Pod가 전혀 생성되지 않고 있습니다. "
                "클러스터 상태를 확인하고 원인을 찾아 정상화하세요."
            ),
            "internal_summary": "nginx Deployment에 존재하지 않는 nodeSelector(disk: ssd-nonexistent)가 설정되어 Pod가 Pending 상태로 스케줄링 불가",
            "fault": {
                "type": "node_selector_mismatch",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"node_selector": {"disk": "ssd-nonexistent"}},
            },
            "expected_solution": {
                "summary": "nginx Deployment의 nodeSelector를 제거한다",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod Pending 상태 (Running/CrashLoop 아님)", "kubectl get pods에서 Pod 없거나 Pending", "describe에서 스케줄링 실패 메시지"],
                "suggested_queries": [],
                "log_signals": ["0/1 nodes are available", "didn't match Pod's node affinity/selector"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 10,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 100, "hint_penalty": 7, "time_limit_seconds": 1200},
        },
        {
            "title": "컨테이너 설정 누락 오류",
            "difficulty": "intermediate",
            "learning_objectives": [
                "Secret과 ConfigMap을 envFrom으로 참조하는 방식을 이해할 수 있다",
                "CreateContainerConfigError 상태를 ImagePullBackOff와 구분하여 진단할 수 있다",
                "kubectl describe로 누락된 리소스를 특정할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 컨테이너 생성 단계에서 계속 실패하고 있습니다. "
                "이미지나 리소스 설정에는 문제가 없어 보입니다. "
                "컨테이너 환경 설정을 자세히 확인하여 원인을 찾으세요."
            ),
            "internal_summary": "nginx Deployment가 존재하지 않는 Secret(missing-app-secret)을 envFrom으로 참조하여 CreateContainerConfigError 발생",
            "fault": {
                "type": "secret_ref_missing",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"secret_name": "missing-app-secret"},
            },
            "expected_solution": {
                "summary": "누락된 Secret을 생성하거나 Deployment에서 envFrom 설정을 제거한다",
                "allowed_fix_patterns": [
                    "kubectl create secret generic missing-app-secret --from-literal=key=value",
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod CreateContainerConfigError 또는 Pending 상태", "describe Events에서 secret 없음 메시지"],
                "suggested_queries": [],
                "log_signals": ["secret \"missing-app-secret\" not found", "CreateContainerConfigError"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 10,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 100, "hint_penalty": 7, "time_limit_seconds": 1200},
        },
        {
            "title": "볼륨 마운트 실패로 Pod 대기 중",
            "difficulty": "intermediate",
            "learning_objectives": [
                "PersistentVolumeClaim의 역할과 상태를 이해할 수 있다",
                "Pod Pending 원인이 스케줄링 실패와 볼륨 바인딩 실패로 다름을 구분할 수 있다",
                "kubectl get pvc로 스토리지 상태를 진단할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 Pending 상태에서 계속 멈춰 있습니다. "
                "노드 리소스에는 여유가 있어 보이는데 Pod가 시작되지 않습니다. "
                "Pod가 왜 스케줄링되지 않는지 확인하세요."
            ),
            "internal_summary": "nginx Deployment가 존재하지 않는 storageClass(nonexistent-storage)의 PVC(nginx-data)를 마운트하여 볼륨 바인딩 실패 → Pod Pending",
            "fault": {
                "type": "pvc_unbound",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "PVC를 삭제하고 Deployment에서 volume/volumeMount 설정을 제거한다",
                "allowed_fix_patterns": [
                    "kubectl delete pvc nginx-data",
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod Pending 상태", "kubectl get pvc에서 nginx-data Pending", "describe에서 volume 바인딩 실패"],
                "suggested_queries": [],
                "log_signals": ["pod has unbound immediate PersistentVolumeClaims", "no persistent volumes available"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 10,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 100, "hint_penalty": 7, "time_limit_seconds": 1200},
        },
    ],
    "advanced": [
        {
            "title": "Pod가 멀쩡한데 계속 재시작됩니다",
            "difficulty": "advanced",
            "learning_objectives": [
                "LivenessProbe와 ReadinessProbe의 동작 차이를 설명할 수 있다",
                "Probe 실패로 인한 container 재시작을 kubectl로 진단할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 Running으로 표시되지만 주기적으로 재시작되고 있습니다. "
                "Pod 내부에는 문제가 없어 보이는데 계속 재시작됩니다. "
                "원인을 찾아 정상화하세요."
            ),
            "internal_summary": "nginx livenessProbe가 존재하지 않는 /healthz-notexist 경로를 확인하여 실패 → container 반복 재시작",
            "fault": {
                "type": "liveness_probe_failure",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"probe_path": "/healthz-notexist"},
            },
            "expected_solution": {
                "summary": "nginx Deployment에서 잘못된 livenessProbe 설정을 제거하거나 올바른 경로로 수정한다",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod restart count 증가", "describe에서 'Liveness probe failed' 이벤트", "RESTARTS 컬럼 증가"],
                "suggested_queries": [
                    'kube_pod_container_status_restarts_total{namespace="{{namespace}}",container="nginx"}'
                ],
                "log_signals": ["Liveness probe failed", "killing container"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 20,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 120, "hint_penalty": 8, "time_limit_seconds": 1500},
        },
        {
            "title": "Pod가 반복해서 재시작됩니다",
            "difficulty": "advanced",
            "learning_objectives": [
                "OOMKilled 상태를 kubectl describe로 진단할 수 있다",
                "컨테이너 메모리 limit의 역할을 이해하고 조정할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 지속적으로 재시작되고 있습니다. "
                "Pod 재시작 원인을 파악하고 안정적으로 운영될 수 있도록 수정하세요."
            ),
            "internal_summary": "nginx 메모리 limit이 6Mi로 제한되어 OOMKilled 반복 발생",
            "fault": {
                "type": "oom_killed",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"memory_limit": "6Mi"},
            },
            "expected_solution": {
                "summary": "nginx Deployment 메모리 limit을 128Mi 이상으로 상향한다",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod restart count 증가", "describe에서 OOMKilled 확인", "메모리 limit 6Mi"],
                "suggested_queries": [
                    'kube_pod_container_resource_limits{namespace="{{namespace}}",container="nginx",resource="memory"}'
                ],
                "log_signals": ["OOMKilled", "exit code 137"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 20,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 120, "hint_penalty": 8, "time_limit_seconds": 1500},
        },
        {
            "title": "Pod가 시작조차 못 합니다",
            "difficulty": "advanced",
            "learning_objectives": [
                "initContainer의 역할과 Pod 시작 순서를 설명할 수 있다",
                "Init:CrashLoopBackOff 상태를 일반 CrashLoopBackOff와 구분하여 진단할 수 있다",
                "kubectl logs -c 옵션으로 특정 컨테이너 로그를 조회할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 항상 Init 상태에서 멈추며 정상 시작되지 않습니다. "
                "컨테이너 자체에는 문제가 없어 보입니다. "
                "Pod 시작 전 단계를 조사하여 원인을 찾고 정상화하세요."
            ),
            "internal_summary": "nginx Deployment에 항상 exit 1로 종료되는 initContainer(init-check)가 추가되어 메인 컨테이너가 시작되지 못함",
            "fault": {
                "type": "init_container_failure",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "nginx Deployment에서 실패하는 initContainer를 제거한다",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod Init:CrashLoopBackOff 상태", "READY 컬럼 0/1 (Init)", "kubectl logs -c init-check 에서 실패 로그"],
                "suggested_queries": [],
                "log_signals": ["prerequisite check failed", "Init:CrashLoopBackOff"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 15,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 130, "hint_penalty": 9, "time_limit_seconds": 1500},
        },
        {
            "title": "이미지 수정 후에도 서비스가 불안정합니다",
            "difficulty": "advanced",
            "learning_objectives": [
                "ImagePullBackOff와 readinessProbe 실패를 순서대로 진단할 수 있다",
                "단일 fix로 해결되지 않는 복합 장애를 끝까지 추적할 수 있다",
                "available_replicas와 ready_replicas의 차이를 이해할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 이미지 문제로 시작되지 않고 있습니다. "
                "문제를 해결했다고 생각했는데 서비스가 여전히 정상화되지 않습니다. "
                "끝까지 원인을 추적하여 완전히 정상화하세요."
            ),
            "internal_summary": "nginx:wrongtag 이미지 오류 + readinessProbe /healthz-notexist 경로 오류 동시 존재. 이미지 수정 후 readinessProbe 실패가 드러남",
            "fault": {
                "type": "compound_probe_cascade",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "1단계: nginx 이미지를 nginx:latest로 수정 / 2단계: readinessProbe 제거 또는 올바른 경로로 수정",
                "allowed_fix_patterns": [
                    "kubectl set image deployment/nginx nginx=nginx:latest",
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": [
                    "1차: ImagePullBackOff",
                    "이미지 수정 후: Pod Running이지만 READY 0/1",
                    "describe에서 Readiness probe failed 이벤트",
                ],
                "suggested_queries": [],
                "log_signals": ["ErrImagePull", "Readiness probe failed"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_fully_available",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 20,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 140, "hint_penalty": 10, "time_limit_seconds": 1800},
        },
        {
            "title": "Pod가 뜨는데 Ready가 안 됩니다",
            "difficulty": "advanced",
            "learning_objectives": [
                "CPU throttling이 컨테이너 동작에 미치는 영향을 이해할 수 있다",
                "리소스 limit과 readinessProbe의 상호작용을 진단할 수 있다",
                "kubectl describe와 kubectl top으로 리소스 병목을 파악할 수 있다",
            ],
            "student_brief": (
                "nginx Pod가 Running으로 표시되지만 Ready 상태가 되지 않아 트래픽을 받지 못하고 있습니다. "
                "이미지나 설정 파일에는 문제가 없어 보입니다. "
                "Pod 리소스 설정을 자세히 조사하세요."
            ),
            "internal_summary": "nginx CPU limit이 1m(1 millicpu)으로 극도로 제한되고 빡빡한 readinessProbe가 설정되어 헬스체크 timeout → 0/1 Not Ready",
            "fault": {
                "type": "cpu_throttle",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "nginx Deployment의 CPU limit을 적절한 값으로 상향하고 readinessProbe를 제거하거나 timeout을 늘린다",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl edit deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod Running이지만 READY 0/1", "describe에서 Readiness probe failed", "CPU limits 1m으로 설정됨"],
                "suggested_queries": [],
                "log_signals": ["Readiness probe failed", "context deadline exceeded"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 15,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 130, "hint_penalty": 9, "time_limit_seconds": 1500},
        },
    ],
    "expert": [
        {
            "title": "nginx 설정 오류로 서버가 불능 상태",
            "difficulty": "expert",
            "learning_objectives": [
                "ConfigMap과 volume mount의 관계를 이해할 수 있다",
                "nginx.conf 문법 오류를 logs로 진단하고 수정할 수 있다",
                "ConfigMap 수정 후 rollout restart를 적용할 수 있다",
            ],
            "student_brief": (
                "nginx 서버가 시작 직후 계속 재시작되고 있습니다. "
                "Pod 이미지나 리소스에는 문제가 없어 보입니다. "
                "로그와 설정을 상세히 확인하여 원인을 찾고 정상화하세요."
            ),
            "internal_summary": (
                "nginx-broken-config ConfigMap에 문법 오류(세미콜론 누락, 닫는 중괄호 누락)가 있는 nginx.conf가 "
                "Deployment에 마운트되어 nginx config test 실패 → CrashLoopBackOff"
            ),
            "fault": {
                "type": "configmap_misconfig",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "nginx-broken-config ConfigMap의 nginx.conf 내용을 올바르게 수정하거나 volumeMount를 제거한 뒤 rollout restart",
                "allowed_fix_patterns": [
                    "kubectl edit configmap nginx-broken-config",
                    "kubectl patch deployment nginx",
                    "kubectl rollout restart deployment/nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod CrashLoopBackOff", "logs에서 nginx config test 실패 메시지", "describe에서 ConfigMap mount 확인"],
                "suggested_queries": [],
                "log_signals": ["nginx: [emerg]", "configuration file test failed", "nginx: configuration file /etc/nginx/nginx.conf test failed"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_deployment_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 30,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 150, "hint_penalty": 10, "time_limit_seconds": 1800},
        },
        {
            "title": "배포 후 간헐적으로 503 오류가 발생합니다",
            "difficulty": "expert",
            "learning_objectives": [
                "Readiness Probe 실패가 트래픽 라우팅에 미치는 영향을 설명할 수 있다",
                "Service Endpoint와 Pod readiness의 연관성을 이해할 수 있다",
                "Probe 설정 오류를 kubectl로 진단하고 수정할 수 있다",
            ],
            "student_brief": (
                "최근 배포 후 nginx 서비스에서 간헐적인 503 오류가 발생합니다. "
                "Pod는 Running 상태로 보이지만 트래픽이 정상 처리되지 않습니다. "
                "원인을 찾아 정상화하세요."
            ),
            "internal_summary": (
                "nginx Deployment에 존재하지 않는 경로를 확인하는 readinessProbe가 설정되어 "
                "Pod가 Ready 상태가 되지 않아 Service Endpoint에서 제외됨."
            ),
            "fault": {
                "type": "probe_failure",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"probe_path": "/healthz-notexist"},
            },
            "expected_solution": {
                "summary": "nginx Deployment의 readinessProbe를 제거하거나 올바른 경로로 수정한다",
                "allowed_fix_patterns": [
                    "kubectl set image deployment/nginx nginx=nginx:latest",
                    "kubectl edit deployment nginx",
                    "kubectl patch deployment nginx",
                ],
            },
            "observability": {
                "symptoms": ["Pod Running이지만 Ready 0/1", "Endpoints에서 Pod 제외됨", "describe에서 Probe 실패"],
                "suggested_queries": [
                    'kube_pod_container_status_ready{namespace="{{namespace}}",container="nginx"}'
                ],
                "log_signals": ["Readiness probe failed", "connection refused"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_pod_ready",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 30,
                    }
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 150, "hint_penalty": 10, "time_limit_seconds": 1800},
        },
        {
            "title": "두 개의 서비스가 동시에 장애입니다",
            "difficulty": "expert",
            "learning_objectives": [
                "독립적인 두 장애를 동시에 발견하고 각각 진단할 수 있다",
                "Deployment 장애와 Service 장애를 구분하여 조사할 수 있다",
                "한 문제를 고친 후 다른 문제가 남아있음을 인지하고 계속 조사할 수 있다",
            ],
            "student_brief": (
                "클러스터에 복수의 이상 징후가 감지되고 있습니다. "
                "어떤 리소스에 어떤 문제가 있는지 스스로 파악하고, "
                "모든 서비스가 정상화될 때까지 조사와 수정을 반복하세요."
            ),
            "internal_summary": (
                "장애 1: nginx Deployment command가 'exit 1'로 설정되어 CrashLoopBackOff. "
                "장애 2: webapp-svc Service selector가 app=webapp-broken으로 설정되어 Endpoints 없음. "
                "두 문제가 완전히 독립적이며 각각 별도 조사 및 fix 필요."
            ),
            "fault": {
                "type": "compound_crash_service",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {},
            },
            "expected_solution": {
                "summary": "1단계: nginx Deployment의 잘못된 command 제거 / 2단계: webapp-svc selector를 app=webapp으로 수정",
                "allowed_fix_patterns": [
                    "kubectl patch deployment nginx",
                    "kubectl patch service webapp-svc",
                    "kubectl edit deployment nginx",
                    "kubectl edit service webapp-svc",
                ],
            },
            "observability": {
                "symptoms": [
                    "nginx Pod CrashLoopBackOff",
                    "webapp-svc Endpoints 비어 있음",
                    "kubectl get pods / get svc / get endpoints 모두 확인 필요",
                ],
                "suggested_queries": [],
                "log_signals": ["exit code 1", "no endpoints available"],
            },
            "validation": {
                "rules": [
                    {
                        "name": "nginx_running",
                        "type": "k8s",
                        "query": "deployment:nginx:running",
                        "stability_seconds": 15,
                    },
                    {
                        "name": "webapp_svc_endpoints",
                        "type": "k8s",
                        "query": "service:webapp-svc:endpoints",
                        "stability_seconds": 15,
                    },
                ],
                "all_required": True,
            },
            "scoring": {"base_score": 200, "hint_penalty": 15, "time_limit_seconds": 2400},
        },
    ],
}


def _sandbox_fixture(environment: str, difficulty: str, fault_type: str) -> dict:
    labels = {
        "docker_network_disconnect": ("컨테이너 네트워크 단절", "training-net 연결 상태"),
        "docker_container_stopped": ("컨테이너 예기치 않은 중지", "training-app 실행 상태"),
        "docker_cpu_throttle": ("컨테이너 CPU 제한", "CPU 사용률과 제한값"),
        "linux_disk_pressure": ("Linux 디스크 압박", "작업 경로 사용률"),
        "linux_cpu_saturation": ("Linux CPU 포화", "load와 CPU 사용률"),
        "linux_process_flood": ("Linux 프로세스 급증", "프로세스 개수와 상태"),
    }
    title, observation = labels[fault_type]
    score = {"beginner": 80, "intermediate": 110, "advanced": 150, "expert": 200}.get(
        difficulty, 80
    )
    return {
        "environment": environment,
        "title": title,
        "difficulty": difficulty,
        "learning_objectives": [f"{environment} 환경에서 {observation}을 관찰하고 복구할 수 있다"],
        "student_brief": f"훈련 환경에 장애가 발생했습니다. {observation}을 확인하고 정상화하세요.",
        "internal_summary": f"{fault_type} fixture 장애",
        "fault": {"type": fault_type, "parameters": {}},
        "expected_solution": {"summary": "허용된 환경 명령으로 정상 상태를 복구한다", "allowed_fix_patterns": []},
        "observability": {"symptoms": [observation], "suggested_queries": [], "log_signals": []},
        "validation": {
            "rules": [{
                "name": f"{fault_type}_resolved", "type": "mock",
                "query": f"{environment}:{fault_type}:resolved", "stability_seconds": 5,
            }],
            "all_required": True,
        },
        "scoring": {"base_score": score, "hint_penalty": 7, "time_limit_seconds": 1200},
    }


_SANDBOX_FAULTS = {
    "docker": ("docker_network_disconnect", "docker_container_stopped", "docker_cpu_throttle"),
    "linux": ("linux_disk_pressure", "linux_cpu_saturation", "linux_process_flood"),
}
_MOCK_FIXTURES_BY_ENVIRONMENT: dict[str, dict[str, list[dict]]] = {
    "kubernetes": _MOCK_FIXTURES,
    **{
        environment: {
            difficulty: [
                _sandbox_fixture(environment, difficulty, fault_type)
                for fault_type in fault_types
            ]
            for difficulty in ("beginner", "intermediate", "advanced", "expert")
        }
        for environment, fault_types in _SANDBOX_FAULTS.items()
    },
}


def _score_candidate(candidate: dict, gen_input: ScenarioGenerationInput) -> float:
    score = 50.0
    fault_type = candidate.get("fault", {}).get("type", "")

    # 최근에 풀지 않은 장애 유형 가산
    if fault_type not in gen_input.recent_fault_types:
        score += 20.0

    # 난이도 일치 가산
    if candidate.get("difficulty") == gen_input.difficulty:
        score += 15.0

    # 관찰 가능성 가산
    if candidate.get("observability", {}).get("symptoms"):
        score += 10.0

    return score


class MockScenarioAgent:
    """개발/테스트용 Mock 에이전트 (fixture 기반, OpenAI 불필요)."""

    def generate(self, gen_input: ScenarioGenerationInput) -> list[ScenarioCandidate]:
        environment_fixtures = _MOCK_FIXTURES_BY_ENVIRONMENT.get(gen_input.environment)
        if environment_fixtures is None:
            raise ValueError(f"지원하지 않는 시나리오 환경입니다: {gen_input.environment}")
        if not gen_input.allowed_fault_types:
            raise ValueError(f"'{gen_input.environment}' 환경의 허용 fault type 목록이 비어 있습니다")
        fixtures = environment_fixtures.get(
            gen_input.difficulty, environment_fixtures["beginner"]
        )

        # allowed_fault_types 필터링
        valid = [
            f for f in fixtures
            if f.get("fault", {}).get("type") in gen_input.allowed_fault_types
        ]
        if not valid:
            raise ValueError(
                f"'{gen_input.environment}' 환경에서 허용된 fixture를 찾을 수 없습니다"
            )

        candidates = []
        for fixture in valid[:3]:
            scenario = deepcopy(fixture)
            scenario["environment"] = gen_input.environment
            score = _score_candidate(scenario, gen_input)
            candidates.append(ScenarioCandidate(scenario=scenario, score=score))

        return candidates


_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class OpenAIScenarioAgent:
    """OpenAI 또는 Gemini OpenAI-호환 엔드포인트 기반 시나리오 생성."""

    _SYSTEM_PROMPT_PATH = os.path.join(
        os.path.dirname(__file__), "../../../ai-data/prompts/scenario_gen.md"
    )

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str | None = None):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            with open(self._SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "You are a multi-environment chaos scenario generator. Return JSON scenario candidates."

    def generate(self, gen_input: ScenarioGenerationInput) -> list[ScenarioCandidate]:
        try:
            import openai
            client_kwargs: dict = {"api_key": self._api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            client = openai.OpenAI(**client_kwargs)

            user_message = self._build_user_message(gen_input)

            response = client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=3000,
                temperature=0.8,
                timeout=30.0,
            )

            raw = response.choices[0].message.content
            return self._parse_response(raw, gen_input)

        except Exception as e:
            print(f"[ScenarioAgent] OpenAI 호출 실패, mock fallback: {e}")
            return MockScenarioAgent().generate(gen_input)

    def _build_user_message(self, gen_input: ScenarioGenerationInput) -> str:
        recent = ", ".join(gen_input.recent_fault_types) if gen_input.recent_fault_types else "없음"
        allowed = ", ".join(gen_input.allowed_fault_types)
        return (
            f"환경: {gen_input.environment}\n"
            f"난이도: {gen_input.difficulty}\n"
            f"사용자 namespace: {gen_input.namespace}\n"
            f"최근 풀었던 fault type (중복 피할 것): {recent}\n"
            f"허용된 fault type 목록: {allowed}\n\n"
            f"위 조건과 동일한 환경의 장애 시나리오 후보 3개를 JSON으로 생성해주세요.\n"
            f"반드시 JSON 객체 형태로 응답하세요: {{\"scenarios\": [...]}}"
        )

    def _parse_response(
        self, raw: str, gen_input: ScenarioGenerationInput
    ) -> list[ScenarioCandidate]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[ScenarioAgent] JSON 파싱 실패: {e}")
            return MockScenarioAgent().generate(gen_input)

        # {"scenarios": [...]} 또는 배열 직접 처리
        if isinstance(data, dict):
            scenarios = data.get("scenarios", data.get("candidates", []))
            if not scenarios:
                # 딕셔너리 자체가 단일 시나리오인 경우
                scenarios = [data]
        elif isinstance(data, list):
            scenarios = data
        else:
            return MockScenarioAgent().generate(gen_input)

        candidates = []
        for s in scenarios[:3]:
            if not isinstance(s, dict):
                continue
            # 필수 필드 검증
            if not all(k in s for k in ("title", "student_brief", "fault", "validation")):
                continue
            if s.get("environment") != gen_input.environment:
                continue
            # namespace placeholder 확인
            fault_str = json.dumps(s.get("fault", {}))
            if gen_input.environment == "kubernetes" and "{{namespace}}" not in fault_str and "namespace" not in fault_str:
                continue

            score = _score_candidate(s, gen_input)
            candidates.append(ScenarioCandidate(scenario=s, score=score))

        if not candidates:
            print("[ScenarioAgent] 유효한 후보 없음, mock fallback")
            return MockScenarioAgent().generate(gen_input)

        return candidates


def get_scenario_agent() -> MockScenarioAgent | OpenAIScenarioAgent:
    if settings.AI_BACKEND == "gemini" and settings.GEMINI_API_KEY:
        return OpenAIScenarioAgent(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            base_url=_GEMINI_BASE_URL,
        )
    if settings.AI_BACKEND == "openai" and settings.OPENAI_API_KEY:
        return OpenAIScenarioAgent(
            api_key=settings.OPENAI_API_KEY,
            model=settings.SCENARIO_MODEL,
        )
    return MockScenarioAgent()
