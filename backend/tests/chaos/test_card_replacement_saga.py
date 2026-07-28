from __future__ import annotations

from app.domain.models import Address
from app.integrations.circuit_breaker import CircuitBreaker
from app.integrations.mocks.fault_injection import FaultInjectionConfig, FaultInjector
from app.integrations.mocks.mock_card_fulfillment import MockCardFulfillmentAdapter
from app.orchestration.flows.card_replacement_flow import CardReplacementSaga

ADDRESS = Address(line1="1 Infinite Loop", city="Cupertino", state_or_province="CA",
                   postal_code="95014", country="US")


class TestCardReplacementSagaHappyPath:
    def test_stolen_card_blocks_then_ships(self):
        fulfillment = MockCardFulfillmentAdapter()
        saga = CardReplacementSaga(fulfillment)

        result = saga.run(
            card_ref="card_1", account_ref="acct_1", reason="stolen",
            shipping_address=ADDRESS, block_idempotency_key="blk-1",
            ship_idempotency_key="ship-1",
        )

        assert result.status == "completed"
        assert result.block_result is not None
        assert fulfillment.is_blocked("card_1")
        assert len(fulfillment.shipments_for("acct_1")) == 1

    def test_damaged_card_ships_without_blocking(self):
        fulfillment = MockCardFulfillmentAdapter()
        saga = CardReplacementSaga(fulfillment)

        result = saga.run(
            card_ref="card_1", account_ref="acct_1", reason="damaged",
            shipping_address=ADDRESS, block_idempotency_key="blk-1",
            ship_idempotency_key="ship-1",
        )

        assert result.status == "completed"
        assert result.block_result is None
        assert not fulfillment.is_blocked("card_1")


class TestCardReplacementSagaFaultInjection:
    def test_fulfillment_failure_after_containment_reports_block_only_escalated(self):
        """§6.3: if containment succeeds but fulfillment fails, the
        customer must never be left with neither a working card nor a
        replacement in motion -- this must come back as a distinct status
        the orchestrator can auto-escalate on, not a generic exception.

        Containment (block) and fulfillment (ship) need *independent*
        fault injectors here -- a single shared one at fault_rate=1.0
        would fail containment too, which isn't the scenario §6.3
        describes and isn't what this test is meant to prove.
        """
        never_fails = FaultInjector(FaultInjectionConfig(fault_rate=0.0, latency_ms=0))
        always_fails = FaultInjector(FaultInjectionConfig(fault_rate=1.0, latency_ms=0))
        fulfillment = MockCardFulfillmentAdapter(
            block_fault_injector=never_fails, ship_fault_injector=always_fails
        )
        saga = CardReplacementSaga(
            fulfillment, fulfillment_breaker=CircuitBreaker(failure_threshold=10), max_attempts=2
        )

        result = saga.run(
            card_ref="card_1", account_ref="acct_1", reason="stolen",
            shipping_address=ADDRESS, block_idempotency_key="blk-1",
            ship_idempotency_key="ship-1",
        )

        assert result.status == "block_only_escalated"
        assert fulfillment.is_blocked("card_1")  # containment still happened
        assert result.fulfillment_result is None

    def test_retry_recovers_from_transient_fulfillment_fault(self):
        """~50% fault rate with enough attempts should usually recover;
        seeded RNG makes this deterministic rather than flaky."""
        import random

        flaky = FaultInjector(
            FaultInjectionConfig(fault_rate=0.6, latency_ms=0), rng=random.Random(42)
        )
        fulfillment = MockCardFulfillmentAdapter(fault_injector=flaky)
        saga = CardReplacementSaga(fulfillment, max_attempts=8)

        result = saga.run(
            card_ref="card_1", account_ref="acct_1", reason="damaged",
            shipping_address=ADDRESS, block_idempotency_key="blk-1",
            ship_idempotency_key="ship-1",
        )

        assert result.status == "completed"

    def test_containment_bypasses_fault_injection_scope_correctly(self):
        """block_card and order_replacement share the same FaultInjector
        instance in this test on purpose -- confirms containment is
        attempted (and can itself fail) independently of fulfillment,
        rather than the saga assuming containment always succeeds."""
        always_fails = FaultInjector(FaultInjectionConfig(fault_rate=1.0, latency_ms=0))
        fulfillment = MockCardFulfillmentAdapter(fault_injector=always_fails)
        saga = CardReplacementSaga(fulfillment)

        import pytest
        from app.integrations.mocks.fault_injection import BackendUnavailableError

        with pytest.raises(BackendUnavailableError):
            saga.contain_if_stolen("card_1", "stolen", "blk-1")
