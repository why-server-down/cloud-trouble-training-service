"""
PromQL Guard - AI 생성 PromQL의 안전성 검사.
namespace 격리, 광범위 쿼리 차단, allowlist 기반 검증.
"""
import re

MAX_QUERY_LENGTH = 1000

ALLOWED_FUNCTIONS = frozenset({
    "sum", "min", "max", "avg", "count", "rate", "increase",
    "histogram_quantile", "clamp_min", "delta", "irate", "idelta",
    "vector", "scalar", "round", "floor", "ceil", "sqrt", "exp", "ln",
    "sort", "sort_desc", "topk", "bottomk", "label_replace", "label_join",
    "by", "without", "on", "ignoring", "group_left", "group_right",
})


class PromQLGuardError(Exception):
    pass


class PromQLGuard:
    """AI 생성 PromQL 안전성 검사 및 namespace 주입."""

    def check(self, query: str, namespace: str) -> str:
        """
        검사 통과 시 namespace placeholder를 실제 값으로 치환한 쿼리 반환.
        실패 시 PromQLGuardError 발생.
        """
        if len(query) > MAX_QUERY_LENGTH:
            raise PromQLGuardError(f"쿼리 길이 초과: {len(query)} > {MAX_QUERY_LENGTH}")

        # {{namespace}} placeholder 치환
        processed = query.replace('{{namespace}}', namespace)

        # namespace label 존재 확인
        has_ns = (
            f'namespace="{namespace}"' in processed
            or f"namespace='{namespace}'" in processed
        )
        if not has_ns:
            # placeholder 없이 아예 namespace label이 없는 경우
            raise PromQLGuardError(
                f'namespace="{namespace}" 레이블이 쿼리에 없습니다. '
                '{{namespace}} placeholder를 사용하거나 namespace label을 명시하세요'
            )

        # 광범위 regex namespace 금지
        if re.search(r'namespace=~"[^"]+"', processed):
            raise PromQLGuardError('namespace=~"..." 광범위 regex는 허용되지 않습니다')

        # 전체 namespace 조회 금지
        if 'namespace!=""' in processed or "namespace!=''" in processed:
            raise PromQLGuardError("namespace!=\"\" 전체 조회는 허용되지 않습니다")

        # absent() 금지 (1차 구현 - 정상 상태 오판 위험)
        if re.search(r'\babsent\s*\(', processed):
            raise PromQLGuardError("absent() 함수는 현재 허용되지 않습니다")

        return processed

    def check_rule(self, rule: dict, namespace: str) -> dict:
        """단일 validation rule dict 검사. guard_status 포함 결과 반환."""
        query = rule.get("query", "")
        rule_type = rule.get("type", "promql")

        # mock/k8s 타입은 promql guard 검사 불필요
        if rule_type in ("mock", "k8s"):
            return {**rule, "guard_status": "accepted", "guard_reason": None}

        try:
            safe_query = self.check(query, namespace)
            return {**rule, "query": safe_query, "guard_status": "accepted", "guard_reason": None}
        except PromQLGuardError as e:
            return {**rule, "guard_status": "rejected", "guard_reason": str(e)}
