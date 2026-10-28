"""
Retry with exponential backoff and jitter.

Concept:
  * Exponential backoff: wait 1s, 2s, 4s, 8s ... between attempts, so a
    struggling server gets breathing room instead of being hammered.
  * Jitter: add a little randomness so 50 workers that failed together don't
    all retry at the exact same moment (the "thundering herd" problem).
  * Only retry what is retryable (see errors.is_transient).
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Delay before retry number `attempt` (1-based): base * 2^(attempt-1), capped, with jitter."""
    raw = min(cap, base * (2 ** (attempt - 1)))
    return raw * random.uniform(0.5, 1.0)


def retry_call(
    fn: Callable[[], T],
    *,
    max_attempts: int,
    is_retryable: Callable[[BaseException], bool],
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """
    Call fn() until it succeeds or we run out of attempts.
    Returns (result, attempts_used). Re-raises the last error on final failure.
    `sleep` is injectable so tests don't actually wait.
    """
    attempt = 1
    while True:
        try:
            return fn(), attempt
        except Exception as exc:  # noqa: BLE001 — we re-raise below
            if attempt >= max_attempts or not is_retryable(exc):
                raise
            delay = backoff_delay(attempt, base_delay)
            if on_retry:
                on_retry(attempt, exc, delay)
            sleep(delay)
            attempt += 1