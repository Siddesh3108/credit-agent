"""Simulates the receiving backend's idempotency behavior (§8.2): a
retried request carrying a previously-seen key returns the original
result rather than repeating the effect."""
from __future__ import annotations

import threading


class InMemoryIdempotencyStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._results: dict = {}

    def get_or_set(self, key: str, compute):
        with self._lock:
            if key in self._results:
                return self._results[key], True  # (result, was_replayed)
            result = compute()
            self._results[key] = result
            return result, False
