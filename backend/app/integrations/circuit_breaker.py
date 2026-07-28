"""Circuit breaker (§8.3): opens after N consecutive failures in a window,
fails fast, half-opens on a timer."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    window_seconds: float = 10.0
    reset_timeout_seconds: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic)

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_timestamps: list = field(default_factory=list, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if self.clock() - self._opened_at >= self.reset_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def call(self, fn: Callable[[], T]) -> T:
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError("circuit breaker is open")
        try:
            result = fn()
        except Exception:
            self._record_failure()
            raise
        else:
            self._record_success()
            return result

    def _record_failure(self) -> None:
        now = self.clock()
        self._failure_timestamps.append(now)
        self._failure_timestamps = [
            t for t in self._failure_timestamps if now - t <= self.window_seconds
        ]
        if len(self._failure_timestamps) >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = now

    def _record_success(self) -> None:
        # A successful call while HALF_OPEN closes the circuit again; a
        # successful call while CLOSED just resets the failure window.
        self._failure_timestamps.clear()
        self._state = CircuitState.CLOSED
        self._opened_at = None
