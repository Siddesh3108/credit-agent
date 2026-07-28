"""Adapter Protocols (§8.1). Every implementation -- real or mock --
satisfies the same Protocol, so the orchestrator, policy engine, and
tests never know or care whether they're talking to production core
banking or a local mock."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import (
    AccountSnapshot,
    Address,
    CreditProfile,
    ExecutionResult,
    RiskScore,
)


class CoreBankingAdapter(Protocol):
    def get_account_summary(self, account_ref: str) -> AccountSnapshot: ...
    def reverse_fee(self, account_ref: str, fee_id: str, idempotency_key: str) -> ExecutionResult: ...
    def get_credit_profile(self, account_ref: str) -> CreditProfile: ...
    def update_credit_limit(
        self, account_ref: str, new_limit: float, reason_code: str, idempotency_key: str
    ) -> ExecutionResult: ...


class CardFulfillmentAdapter(Protocol):
    def block_card(self, card_ref: str, reason: str, idempotency_key: str) -> ExecutionResult: ...
    def order_replacement(
        self,
        account_ref: str,
        reason: str,
        shipping_address: Address,
        expedited: bool,
        idempotency_key: str,
    ) -> ExecutionResult: ...


class FraudServiceAdapter(Protocol):
    def score_risk(self, account_ref: str) -> RiskScore: ...
    def is_sanctioned_destination(self, address: Address) -> bool: ...
    def flag_velocity(self, account_ref: str, event_type: str) -> bool: ...


class NotificationAdapter(Protocol):
    def send(self, customer_ref: str, template: str, context: dict) -> ExecutionResult: ...
