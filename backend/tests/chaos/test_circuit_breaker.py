from __future__ import annotations

from app.integrations.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from app.integrations.retry import retry_with_backoff


class FakeClock:
    """Deterministic, manually-advanced clock so circuit-breaker timing
    tests don't need real wall-clock sleeps."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestCircuitBreaker:
    def test_stays_closed_below_failure_threshold(self):
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=5, window_seconds=10, clock=clock)

        for _ in range(4):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except RuntimeError:
                pass

        assert breaker.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures_in_window(self):
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=5, window_seconds=10, clock=clock)

        for _ in range(5):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except RuntimeError:
                pass

        assert breaker.state == CircuitState.OPEN

    def test_open_circuit_fails_fast_without_calling_fn(self):
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=1, window_seconds=10, clock=clock)
        calls = []

        try:
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except RuntimeError:
            pass
        assert breaker.state == CircuitState.OPEN

        import pytest
        with pytest.raises(CircuitOpenError):
            breaker.call(lambda: calls.append(1))
        assert calls == []  # fn was never invoked -- failed fast

    def test_failures_outside_window_do_not_accumulate(self):
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=3, window_seconds=10, clock=clock)

        for _ in range(2):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except RuntimeError:
                pass
        clock.advance(11)  # older failures fall outside the 10s window
        try:
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except RuntimeError:
            pass

        assert breaker.state == CircuitState.CLOSED

    def test_half_opens_after_reset_timeout_then_closes_on_success(self):
        clock = FakeClock()
        breaker = CircuitBreaker(
            failure_threshold=1, window_seconds=10, reset_timeout_seconds=30, clock=clock
        )
        try:
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except RuntimeError:
            pass
        assert breaker.state == CircuitState.OPEN

        clock.advance(31)
        assert breaker.state == CircuitState.HALF_OPEN

        result = breaker.call(lambda: "ok")
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED


class TestRetryWithBackoff:
    def test_succeeds_without_retry_when_first_call_works(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return "ok"

        result = retry_with_backoff(fn, max_attempts=3, sleep=lambda s: None)
        assert result == "ok"
        assert calls["n"] == 1

    def test_retries_up_to_max_attempts_then_raises(self):
        calls = {"n": 0}

        def always_fails():
            calls["n"] += 1
            raise RuntimeError("still down")

        import pytest
        with pytest.raises(RuntimeError):
            retry_with_backoff(always_fails, max_attempts=3, sleep=lambda s: None)
        assert calls["n"] == 3

    def test_succeeds_after_transient_failures(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "recovered"

        result = retry_with_backoff(flaky, max_attempts=5, sleep=lambda s: None)
        assert result == "recovered"
        assert calls["n"] == 3

    def test_backoff_delays_increase_and_are_bounded(self):
        delays = []

        def always_fails():
            raise RuntimeError("down")

        import pytest
        with pytest.raises(RuntimeError):
            retry_with_backoff(
                always_fails, max_attempts=4, base_delay_seconds=0.1, max_delay_seconds=1.0,
                jitter_seconds=0.0, sleep=lambda s: delays.append(s),
            )
        # 3 sleeps between 4 attempts: 0.1, 0.2, 0.4 (exponential, no jitter here)
        assert delays == [0.1, 0.2, 0.4]
