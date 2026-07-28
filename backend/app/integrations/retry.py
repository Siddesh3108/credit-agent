"""Bounded retry with exponential backoff + jitter (§8.3)."""
from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.1,
    max_delay_seconds: float = 2.0,
    jitter_seconds: float = 0.05,
    retryable: tuple = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> T:
    rng = rng or random.Random()
    attempt = 0
    while True:
        try:
            return fn()
        except retryable:
            attempt += 1
            if attempt >= max_attempts:
                raise
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), max_delay_seconds)
            delay += rng.uniform(0, jitter_seconds)
            sleep(delay)
