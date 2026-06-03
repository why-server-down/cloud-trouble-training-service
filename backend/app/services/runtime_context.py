"""
RuntimeContextCollector - AI 튜터가 현재 클러스터 상태를 보고 답할 수 있도록
K8s / Prometheus / Loki / CommandLog를 수집해 컨텍스트 dict로 반환.

Phase 1: CommandLog 요약 + 기본 구조
Phase 4: K8s state, Prometheus validation, Loki log 수집 추가 예정
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommandLog, TerminalSession


class RuntimeContextCollector:

    async def collect(
        self,
        user_id: uuid.UUID,
        namespace: str,
        db: AsyncSession,
        scenario_title: str = "",
        student_brief: str = "",
        difficulty: str = "",
    ) -> dict:
        recent_commands = await self._collect_recent_commands(user_id, db)

        return {
            "namespace": namespace,
            "mission": {
                "title": scenario_title,
                "difficulty": difficulty,
                "student_brief": student_brief,
            },
            "recent_user_commands": recent_commands,
            # Phase 4에서 추가 예정
            "kubernetes_state": None,
            "prometheus": None,
            "loki": None,
        }

    async def _collect_recent_commands(
        self, user_id: uuid.UUID, db: AsyncSession, limit: int = 10
    ) -> list[dict]:
        result = await db.execute(
            select(TerminalSession)
            .where(TerminalSession.user_id == user_id, TerminalSession.is_active == True)  # noqa: E712
            .order_by(TerminalSession.last_activity.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if not session:
            return []

        logs_result = await db.execute(
            select(CommandLog)
            .where(CommandLog.session_id == session.id)
            .order_by(CommandLog.executed_at.desc())
            .limit(limit)
        )
        logs = logs_result.scalars().all()

        return [
            {
                "command": log.command,
                "exit_code": log.exit_code,
                "output_summary": log.output[:200] if log.output else "",
            }
            for log in reversed(logs)
        ]


_collector: RuntimeContextCollector | None = None


def get_runtime_context_collector() -> RuntimeContextCollector:
    global _collector
    if _collector is None:
        _collector = RuntimeContextCollector()
    return _collector
