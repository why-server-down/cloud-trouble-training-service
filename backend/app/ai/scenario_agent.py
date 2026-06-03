"""
AI 시나리오 생성 에이전트.
- mock 모드: 난이도별 fixture JSON 반환 (OpenAI 없이 동작)
- openai 모드: Phase 6에서 구현 예정, 현재는 mock fallback
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class ScenarioGenerationInput:
    difficulty: str  # beginner | intermediate | advanced | expert
    namespace: str
    recent_fault_types: list[str]
    allowed_fault_types: list[str]


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
        }
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
        }
    ],
    "advanced": [
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
        }
    ],
    "expert": [
        {
            "title": "배포 후 간헐적으로 503 오류가 발생합니다",
            "difficulty": "expert",
            "learning_objectives": [
                "Readiness Probe 실패가 트래픽 라우팅에 미치는 영향을 설명할 수 있다",
                "Service Endpoint와 Pod readiness의 연관성을 이해할 수 있다",
                "Probe 설정 오류를 kubectl로 진단하고 수정할 수 있다",
            ],
            "student_brief": (
                "최근 배포 후 webapp 서비스에서 간헐적인 503 오류가 발생합니다. "
                "Pod는 Running 상태로 보이지만 트래픽이 정상 처리되지 않습니다. "
                "원인을 찾아 정상화하세요."
            ),
            "internal_summary": (
                "nginx Deployment에 잘못된 이미지 태그가 설정되어 "
                "Pod가 Running 상태가 아닌 장애. Service Endpoint에서 제외됨."
            ),
            "fault": {
                "type": "probe_failure",
                "target": {"kind": "Deployment", "name": "nginx", "namespace": "{{namespace}}"},
                "parameters": {"wrong_image": "nginx:wrongtag", "original_image": "nginx:latest"},
            },
            "expected_solution": {
                "summary": "nginx Deployment 이미지를 올바르게 수정하고 Pod가 Running 상태가 되도록 한다",
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
        }
    ],
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
        fixtures = _MOCK_FIXTURES.get(gen_input.difficulty, _MOCK_FIXTURES["beginner"])

        # allowed_fault_types 필터링
        valid = [
            f for f in fixtures
            if not gen_input.allowed_fault_types
            or f.get("fault", {}).get("type") in gen_input.allowed_fault_types
        ]
        if not valid:
            valid = fixtures

        candidates = []
        for scenario in valid[:3]:
            score = _score_candidate(scenario, gen_input)
            candidates.append(ScenarioCandidate(scenario=scenario, score=score))

        if not candidates:
            fallback = _MOCK_FIXTURES["beginner"][0]
            candidates = [ScenarioCandidate(scenario=fallback, score=30.0)]

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
            return "You are a Kubernetes chaos scenario generator. Return JSON array of 3 scenario candidates."

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
            f"난이도: {gen_input.difficulty}\n"
            f"사용자 namespace: {gen_input.namespace}\n"
            f"최근 풀었던 fault type (중복 피할 것): {recent}\n"
            f"허용된 fault type 목록: {allowed}\n\n"
            f"위 조건에 맞는 Kubernetes 장애 시나리오 후보 3개를 JSON으로 생성해주세요.\n"
            f"반드시 JSON 객체 형태로 응답하세요: {{\"scenarios\": [...]}}"
        )

    def _parse_response(
        self, raw: str, gen_input: ScenarioGenerationInput
    ) -> list[ScenarioCandidate]:
        import json

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
            # namespace placeholder 확인
            fault_str = json.dumps(s.get("fault", {}))
            if "{{namespace}}" not in fault_str and "namespace" not in fault_str:
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
