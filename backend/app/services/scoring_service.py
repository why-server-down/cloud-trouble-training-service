from datetime import datetime, timezone


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
