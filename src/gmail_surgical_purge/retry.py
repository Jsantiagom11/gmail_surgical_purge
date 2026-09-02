"""Bounded backoff and a shared rate limiter for concurrent metadata reads."""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .errors import PurgeError


def retry_delay(attempt: int, retry_after: str | None, *, jitter: float | None = None) -> float:
    delay = min(30.0, 2.0**attempt) + (random.random() if jitter is None else jitter)
    if retry_after:
        try:
            requested = float(retry_after)
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(retry_after)
                requested = (retry_date - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                requested = 0.0
        if math.isfinite(requested):
            if requested > 60:
                raise PurgeError(
                    "Gmail requested a long pause. Resume after the quota window resets."
                )
            delay = max(delay, requested)
    return delay


class RateLimiter:
    def __init__(
        self,
        rate: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < rate <= 40:
            raise ValueError("Rate must be >0 and <=40 requests per second")
        self._interval = 1.0 / rate
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            reserved = max(now, self._next)
            self._next = reserved + self._interval
        delay = reserved - now
        if delay > 0:
            self._sleep(delay)
