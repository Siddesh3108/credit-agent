"""Implements §6.3's card-replacement saga and §8.4's saga pattern generally.

`contain_if_stolen` is exposed as its own method (not folded into `run`)
because §6.3 is explicit that blocking a reported-stolen card is
unconditional and happens before policy evaluation or user confirmation --
the orchestrator node calls it immediately, independent of whatever else
the conversation is doing (§10.7). `run` handles the rest of the saga:
shipping the replacement, with retry + circuit breaker, and reporting a
distinct status when containment succeeded but fulfillment didn't, so the
orchestrator can auto-escalate rather than leave the saga half-complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domain.models import Address
from app.integrations.base_adapter import CardFulfillmentAdapter
from app.integrations.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.integrations.retry import retry_with_backoff

SagaStatus = Literal["completed", "block_only_escalated", "failed"]


@dataclass
class SagaResult:
    block_result: dict | None
    fulfillment_result: dict | None
    status: SagaStatus


class CardReplacementSaga:
    def __init__(
        self,
        card_fulfillment: CardFulfillmentAdapter,
        fulfillment_breaker: CircuitBreaker | None = None,
        max_attempts: int = 3,
    ):
        self._card_fulfillment = card_fulfillment
        self._fulfillment_breaker = fulfillment_breaker or CircuitBreaker()
        self._max_attempts = max_attempts

    def contain_if_stolen(self, card_ref: str, reason: str, idempotency_key: str) -> dict | None:
        if reason != "stolen":
            return None
        result = self._card_fulfillment.block_card(card_ref, reason, idempotency_key)
        return dict(result)

    def ship(
        self,
        *,
        account_ref: str,
        reason: str,
        shipping_address: Address,
        ship_idempotency_key: str,
        expedited: bool = False,
        block_result: dict | None = None,
    ) -> SagaResult:
        """The fulfillment half of the saga on its own -- for callers
        (like execute_action_node) where containment was already run
        separately by an earlier node/step and re-running it here would
        be redundant (even though it would be *safe*, since
        contain_if_stolen is idempotent -- this just avoids doing it
        twice through two different code paths)."""

        def do_ship():
            return self._card_fulfillment.order_replacement(
                account_ref, reason, shipping_address, expedited, ship_idempotency_key
            )

        try:
            fulfillment_result = self._fulfillment_breaker.call(
                lambda: retry_with_backoff(do_ship, max_attempts=self._max_attempts)
            )
        except (CircuitOpenError, Exception):
            status: SagaStatus = "block_only_escalated" if block_result else "failed"
            return SagaResult(block_result=block_result, fulfillment_result=None, status=status)

        return SagaResult(
            block_result=block_result,
            fulfillment_result=dict(fulfillment_result),
            status="completed",
        )

    def run(
        self,
        *,
        card_ref: str,
        account_ref: str,
        reason: str,
        shipping_address: Address,
        block_idempotency_key: str,
        ship_idempotency_key: str,
        expedited: bool = False,
    ) -> SagaResult:
        """Convenience entry point that does containment-then-shipping in
        one call, for callers that haven't already run containment
        separately (e.g. the standalone chaos/contract tests). Delegates
        to `ship()` so there's exactly one implementation of the
        retry/circuit-breaker path and the §6.3 partial-failure handling,
        not two copies that could drift out of sync.

        §6.3: the customer must never be left with neither a working card
        nor a replacement in motion. Containment (if it ran) already
        succeeded and is logged as its own event; `ship()` reports a
        distinct status if fulfillment then fails, so the caller
        auto-escalates rather than leaving the saga half-complete. A
        production version schedules a bounded background retry before
        escalating (§6.3's 2-minute SLA); this reference implementation
        escalates immediately and leaves the retry-then-escalate timing
        to the caller/worker.
        """
        block_result = None
        if reason == "stolen":
            block_result = self.contain_if_stolen(card_ref, reason, block_idempotency_key)

        return self.ship(
            account_ref=account_ref, reason=reason, shipping_address=shipping_address,
            ship_idempotency_key=ship_idempotency_key, expedited=expedited, block_result=block_result,
        )
