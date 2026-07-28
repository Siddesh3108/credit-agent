"""In-memory stand-in for the card fulfillment system (§8.5)."""
from __future__ import annotations

import time

from app.domain.models import Address, ExecutionResult
from app.integrations.mocks.fault_injection import FaultInjector
from app.integrations.mocks.idempotency_store import InMemoryIdempotencyStore


class MockCardFulfillmentAdapter:
    def __init__(
        self,
        fault_injector: FaultInjector | None = None,
        core_banking=None,
        block_fault_injector: FaultInjector | None = None,
        ship_fault_injector: FaultInjector | None = None,
    ):
        """`fault_injector` applies to both operations if given and the
        per-operation overrides are not. Real backends fail independently
        per endpoint, so tests exercising a saga's partial-failure paths
        (§6.3) should use `block_fault_injector` / `ship_fault_injector`
        directly rather than one shared injector.

        `core_banking`, if given, must expose `mark_active_replacement`
        (see MockCoreBankingAdapter) -- called after a shipment is
        created, mirroring §6.3's "sync card status" step back to core
        banking through a real method call rather than shared mutable
        state. Optional so this adapter works standalone in tests that
        don't care about that side effect.
        """
        self._blocked_cards: set[str] = set()
        self._shipments: list[dict] = []
        default = fault_injector or FaultInjector()
        self._block_faults = block_fault_injector or default
        self._ship_faults = ship_fault_injector or default
        self._idempotency = InMemoryIdempotencyStore()
        self._core_banking = core_banking

    def is_blocked(self, card_ref: str) -> bool:
        return card_ref in self._blocked_cards

    def shipments_for(self, account_ref: str) -> list[dict]:
        return [s for s in self._shipments if s["account_ref"] == account_ref]

    def block_card(self, card_ref: str, reason: str, idempotency_key: str) -> ExecutionResult:
        def do_block() -> ExecutionResult:
            self._block_faults.maybe_delay_and_fail()
            self._blocked_cards.add(card_ref)
            return ExecutionResult(
                success=True, backend_reference=f"BLK-{card_ref}", latency_ms=0.0,
                raw_response={"card_ref": card_ref, "reason": reason}, error=None,
            )

        result, _replayed = self._idempotency.get_or_set(idempotency_key, do_block)
        return result

    def order_replacement(
        self,
        account_ref: str,
        reason: str,
        shipping_address: Address,
        expedited: bool,
        idempotency_key: str,
    ) -> ExecutionResult:
        def do_ship() -> ExecutionResult:
            self._ship_faults.maybe_delay_and_fail()
            shipment_id = f"SHIP-{account_ref}-{int(time.time() * 1000)}"
            self._shipments.append({
                "shipment_id": shipment_id, "account_ref": account_ref, "reason": reason,
                "shipping_address": shipping_address, "expedited": expedited,
            })
            if self._core_banking is not None:
                self._core_banking.mark_active_replacement(account_ref, in_transit=True)
            return ExecutionResult(
                success=True, backend_reference=shipment_id, latency_ms=0.0,
                raw_response={"shipment_id": shipment_id, "eta_days": 2 if not expedited else 1},
                error=None,
            )

        result, _replayed = self._idempotency.get_or_set(idempotency_key, do_ship)
        return result
