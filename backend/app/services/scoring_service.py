from datetime import datetime, timezone

# 힌트는 튜터 답의 구체성 단계다(0 질문만 → 3 원인과 복구, ai-data/prompts/socratic_tutor.md).
# 3단계를 넘게 사도 튜터가 더 주는 것이 없으니 감점만 받지 않게 막는다.
MAX_HINT_LEVEL = 3
HINT_LIMIT_MESSAGE = "힌트는 3단계까지입니다. 튜터가 이미 가장 구체적인 단계로 답하고 있습니다."


class ScoringService:
    MIN_SCORE: int = 20
    TIME_PENALTY_PER_MINUTE: int = 2

    def calculate_score(
        self,
        base_score: int,
        start_time: datetime,
        end_time: datetime,
        hints_used: int,
        hint_penalty: int,
    ) -> int:
        elapsed_minutes = (end_time - start_time).total_seconds() / 60.0
        time_deduction = int(elapsed_minutes * self.TIME_PENALTY_PER_MINUTE)
        hint_deduction = hints_used * hint_penalty
        score = base_score - time_deduction - hint_deduction
        return max(score, self.MIN_SCORE)

    def calculate_current_score(
        self,
        base_score: int,
        start_time: datetime,
        hints_used: int,
        hint_penalty: int,
    ) -> int:
        return self.calculate_score(
            base_score, start_time, datetime.now(timezone.utc), hints_used, hint_penalty
        )
