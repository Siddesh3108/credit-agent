"""Configurable latency + fault injection for mock adapters (§8.5), so
resilience code (circuit breakers, retries, sagas) can be exercised in CI
without real banking system access. Controlled via FAULT_RATE / LATENCY_MS
env vars, exactly as §8.5 specifies."""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass


class BackendUnavailableError(RuntimeError):
    pass


@dataclass
class FaultInjectionConfig:
    fault_rate: float = 0.0
    latency_ms: int = 0

    @classmethod
    def from_env(cls, prefix: str = "") -> "FaultInjectionConfig":
        return cls(
            fault_rate=float(os.environ.get(f"{prefix}FAULT_RATE", "0") or 0),
            latency_ms=int(os.environ.get(f"{prefix}LATENCY_MS", "0") or 0),
        )


class FaultInjector:
    def __init__(self, config: FaultInjectionConfig | None = None, rng: random.Random | None = None):
        self._config = config or FaultInjectionConfig.from_env()
        self._rng = rng or random.Random()

    def maybe_delay_and_fail(self) -> None:
        if self._config.latency_ms:
            time.sleep(self._config.latency_ms / 1000)
        if self._config.fault_rate and self._rng.random() < self._config.fault_rate:
            raise BackendUnavailableError("injected fault")
