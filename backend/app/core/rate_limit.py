"""사용자당 요청 빈도 제한.

chat 은 호출마다 LLM 비용이 나간다. 제한이 없으면 한 사용자가 반복 요청만으로
전체 예산을 소진할 수 있다.

인메모리 고정 윈도우다. 서버 인스턴스가 여러 개면 인스턴스마다 따로 센다.
캡스톤 범위(단일 인스턴스)에는 충분하고, 다중 인스턴스로 가면 Redis 같은 공유
저장소가 필요하다.
"""
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """허용되면 None, 초과하면 재시도까지 남은 초를 돌려준다."""
        if self._limit <= 0:
            return None

        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())

        # 윈도우를 벗어난 기록을 버린다. 그래야 메모리가 무한히 늘지 않는다.
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self._limit:
            return round(hits[0] + self._window - now, 1)

        hits.append(now)
        return None

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
