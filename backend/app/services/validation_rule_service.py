"""
ValidationRuleService - AI 생성 검증 조건의 저장, 가드, 실행.
1차 구현: DB 저장 + Prometheus HTTP API query (옵션 A).
Mock 모드: in-memory 해결 상태 추적.
"""
import asyncio
import re
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ValidationRule
from app.services.promql_guard import PromQLGuard


@dataclass
class RuleCheckResult:
    rule_id: uuid.UUID
    name: str
    passed: bool
    last_value: float | None = None
    error: str | None = None


class ValidationRuleService:

    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self._prometheus_url = prometheus_url.rstrip("/")
        self._guard = PromQLGuard()
        self._mock_resolved: set[str] = set()  # "{scenario_id}:{namespace}"

    async def guard_and_store(
        self,
        scenario_id: uuid.UUID,
        validation_json: dict,
        namespace: str,
        db: AsyncSession,
    ) -> list[ValidationRule]:
        """validation JSON의 rules를 guard 검사 후 DB 저장."""
        rules = validation_json.get("rules", [])
        stored: list[ValidationRule] = []

        for rule in rules:
            checked = self._guard.check_rule(rule, namespace)
            vr = ValidationRule(
                scenario_id=scenario_id,
                name=checked.get("name", "unnamed"),
                rule_type=checked.get("type", "promql"),
                query=checked.get("query", ""),
                stability_seconds=int(checked.get("stability_seconds", 0)),
                is_required=bool(checked.get("is_required", True)),
                guard_status=checked["guard_status"],
                guard_reason=checked.get("guard_reason"),
            )
            db.add(vr)
            stored.append(vr)

        # commit은 호출자(ScenarioService)가 담당 - 여기선 flush만
        await db.flush()
        return stored

    async def check_rules(
        self,
        scenario_id: uuid.UUID,
        namespace: str,
        db: AsyncSession,
        use_mock: bool = False,
    ) -> tuple[bool, list[RuleCheckResult]]:
        """저장된 required rule 전체 확인. (all_required 가정)"""
        result = await db.execute(
            select(ValidationRule).where(
                ValidationRule.scenario_id == scenario_id,
                ValidationRule.is_required == True,  # noqa: E712
                ValidationRule.guard_status == "accepted",
            )
        )
        rules = result.scalars().all()

        if not rules:
            # 규칙 없으면 mock 해결 상태로 판단
            resolved = self._is_mock_resolved(scenario_id, namespace)
            return resolved, []

        results: list[RuleCheckResult] = []
        for rule in rules:
            if use_mock or rule.rule_type == "mock":
                passed = self._is_mock_resolved(scenario_id, namespace)
                results.append(RuleCheckResult(rule_id=rule.id, name=rule.name, passed=passed))
            elif rule.rule_type == "promql":
                check = await self._run_promql(rule)
                results.append(check)
            elif rule.rule_type == "k8s":
                check = await self._run_k8s(rule, namespace)
                results.append(check)
            else:
                results.append(RuleCheckResult(
                    rule_id=rule.id, name=rule.name, passed=False, error=f"unsupported rule type: {rule.rule_type}"
                ))

        all_passed = all(r.passed for r in results)
        return all_passed, results

    async def _run_promql(self, rule: ValidationRule) -> RuleCheckResult:
        """Prometheus HTTP API로 PromQL 실행."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._prometheus_url}/api/v1/query",
                    params={"query": rule.query},
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") != "success":
                return RuleCheckResult(rule_id=rule.id, name=rule.name, passed=False, error="prometheus query failed")

            values = data.get("data", {}).get("result", [])
            if not values:
                return RuleCheckResult(rule_id=rule.id, name=rule.name, passed=False, last_value=0.0)

            last_val = float(values[0]["value"][1])
            return RuleCheckResult(rule_id=rule.id, name=rule.name, passed=last_val > 0, last_value=last_val)

        except Exception as e:
            return RuleCheckResult(rule_id=rule.id, name=rule.name, passed=False, error=str(e))

    async def _run_k8s(self, rule: ValidationRule, namespace: str) -> RuleCheckResult:
        """K8s API로 Deployment/Pod 상태 직접 검증. query 형식: 'deployment:nginx:running'"""
        try:
            def _check():
                from kubernetes import client, config as k8s_config
                try:
                    k8s_config.load_incluster_config()
                except Exception:
                    k8s_config.load_kube_config()
                apps_api = client.AppsV1Api()
                core_api = client.CoreV1Api()

                query = rule.query
                parts = [p.strip() for p in query.split(":")]

                if parts[0] == "deployment" and len(parts) >= 3:
                    name, check_type = parts[1], parts[2]
                    dep = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
                    if check_type == "running":
                        available = dep.status.available_replicas or 0
                        return available > 0, float(available)
                    elif check_type == "memory_limit" and len(parts) >= 4:
                        threshold = parts[3]  # e.g. "20Mi"
                        containers = dep.spec.template.spec.containers
                        for c in containers:
                            if c.resources and c.resources.limits:
                                mem = c.resources.limits.get("memory", "0")
                                val = int(re.sub(r"[^0-9]", "", mem) or 0)
                                unit = re.sub(r"[0-9]", "", mem).upper()
                                thresh_val = int(re.sub(r"[^0-9]", "", threshold) or 0)
                                thresh_unit = re.sub(r"[0-9]", "", threshold).upper()
                                multiplier = {"MI": 1, "GI": 1024, "KI": 1 / 1024, "": 1 / (1024 * 1024)}
                                val_mi = val * multiplier.get(unit, 1)
                                thresh_mi = thresh_val * multiplier.get(thresh_unit, 1)
                                return val_mi >= thresh_mi, val_mi
                        return False, 0.0

                elif parts[0] == "service" and len(parts) >= 3:
                    svc_name, check_type = parts[1], parts[2]
                    if check_type == "endpoints":
                        ep = core_api.read_namespaced_endpoints(name=svc_name, namespace=namespace)
                        ready = sum(
                            len(s.addresses or [])
                            for subset in (ep.subsets or [])
                            for s in [subset]
                        )
                        return ready > 0, float(ready)

                return False, 0.0

            passed, value = await asyncio.get_event_loop().run_in_executor(None, _check)
            return RuleCheckResult(rule_id=rule.id, name=rule.name, passed=passed, last_value=value)
        except Exception as e:
            return RuleCheckResult(rule_id=rule.id, name=rule.name, passed=False, error=str(e))

    _FAULT_TYPE_K8S_QUERY: dict[str, str] = {
        "image_pull_error":          "deployment:nginx:running",
        "pod_failure":               "deployment:nginx:running",
        "crash_loop":                "deployment:nginx:running",
        "probe_failure":             "deployment:nginx:running",
        "configmap_misconfig":       "deployment:nginx:running",
        "liveness_probe_failure":    "deployment:nginx:running",
        "init_container_failure":    "deployment:nginx:running",
        "node_selector_mismatch":    "deployment:nginx:running",
        "compound_probe_cascade":    "deployment:nginx:running",  # available_replicas가 두 문제 모두 감지
        "oom_killed":                "deployment:nginx:running",
        "memory_stress":             "deployment:nginx:running",
        "network_latency":           "deployment:nginx:running",
        "wrong_image_registry":      "deployment:nginx:running",
        "secret_ref_missing":        "deployment:nginx:running",
        "pvc_unbound":               "deployment:nginx:running",
        "cpu_throttle":              "deployment:nginx:running",
        "service_selector_mismatch": "service:webapp-svc:endpoints",
        "service_misconfig":         "service:webapp-svc:endpoints",
    }

    # compound 장애는 복수 쿼리 동시 검증
    _COMPOUND_K8S_QUERIES: dict[str, list[str]] = {
        "compound_crash_service": [
            "deployment:nginx:running",
            "service:webapp-svc:endpoints",
        ],
    }

    async def k8s_check_by_fault_type(self, fault_type: str, namespace: str) -> bool:
        """accepted 검증 룰이 없을 때 fault_type 기반 K8s 직접 검증 fallback."""
        # compound 장애: 복수 쿼리 모두 통과해야 resolved
        compound = self._COMPOUND_K8S_QUERIES.get(fault_type)
        if compound:
            results = await asyncio.gather(*[
                self._run_k8s(self._make_fallback_rule(q, fault_type), namespace)
                for q in compound
            ])
            return all(r.passed for r in results)

        query = self._FAULT_TYPE_K8S_QUERY.get(fault_type)
        if not query:
            return False
        result = await self._run_k8s(self._make_fallback_rule(query, fault_type), namespace)
        return result.passed

    def _make_fallback_rule(self, query: str, fault_type: str):
        class _Rule:
            id = uuid.uuid4()
            name = f"fallback_{fault_type}"
        rule = _Rule()
        rule.query = query
        return rule

    def _is_mock_resolved(self, scenario_id: uuid.UUID, namespace: str) -> bool:
        return f"{scenario_id}:{namespace}" in self._mock_resolved

    def mark_resolved(self, scenario_id: uuid.UUID, namespace: str):
        self._mock_resolved.add(f"{scenario_id}:{namespace}")

    def reset(self, scenario_id: uuid.UUID, namespace: str):
        self._mock_resolved.discard(f"{scenario_id}:{namespace}")
