"""In-memory stand-in for the core banking system (§8.5), satisfying the
same `CoreBankingAdapter` Protocol a real implementation would. Seed state
via `seed_account` / `seed_credit_profile` / `seed_fee` before use.
"""
from __future__ import annotations

import time
from dataclasses import replace

from app.domain.models import AccountSnapshot, CreditProfile, ExecutionResult, FeeRecord
from app.integrations.mocks.fault_injection import FaultInjector
from app.integrations.mocks.idempotency_store import InMemoryIdempotencyStore


class UnknownAccountError(KeyError):
    pass


class MockCoreBankingAdapter:
    def __init__(self, fault_injector: FaultInjector | None = None):
        self._accounts: dict[str, AccountSnapshot] = {}
        self._credit_profiles: dict[str, CreditProfile] = {}
        self._fees: dict[str, dict[str, FeeRecord]] = {}
        self._faults = fault_injector or FaultInjector()
        self._idempotency = InMemoryIdempotencyStore()

    # -- seeding (test/dev only) -------------------------------------
    def seed_account(self, account: AccountSnapshot) -> None:
        self._accounts[account.account_ref] = account

    def seed_credit_profile(self, profile: CreditProfile) -> None:
        self._credit_profiles[profile.account_ref] = profile

    def seed_fee(self, account_ref: str, fee: FeeRecord) -> None:
        self._fees.setdefault(account_ref, {})[fee.fee_id] = fee

    def mark_active_replacement(self, account_ref: str, in_transit: bool) -> None:
        """Called by the fulfillment side after a shipment is created,
        mirroring §6.3's "sync card status" step back to core banking in
        a real deployment. A public method rather than a shared dict
        reference, so the two mock adapters interact the way real
        services would (through an interface), not by reaching into each
        other's internals."""
        if account_ref in self._accounts:
            self._accounts[account_ref] = replace(
                self._accounts[account_ref], active_replacement_in_transit=in_transit
            )

    def get_fee(self, account_ref: str, fee_id: str) -> FeeRecord | None:
        return self._fees.get(account_ref, {}).get(fee_id)

    def list_fees(self, account_ref: str) -> list[FeeRecord]:
        return list(self._fees.get(account_ref, {}).values())

    # -- CoreBankingAdapter Protocol ----------------------------------
    def get_account_summary(self, account_ref: str) -> AccountSnapshot:
        self._faults.maybe_delay_and_fail()
        if account_ref not in self._accounts:
            raise UnknownAccountError(account_ref)
        return self._accounts[account_ref]

    def get_credit_profile(self, account_ref: str) -> CreditProfile:
        self._faults.maybe_delay_and_fail()
        if account_ref not in self._credit_profiles:
            raise UnknownAccountError(account_ref)
        return self._credit_profiles[account_ref]

    def reverse_fee(self, account_ref: str, fee_id: str, idempotency_key: str) -> ExecutionResult:
        def do_reverse() -> ExecutionResult:
            self._faults.maybe_delay_and_fail()
            fee = self.get_fee(account_ref, fee_id)
            if fee is None:
                return ExecutionResult(
                    success=False, backend_reference="", latency_ms=0.0,
                    raw_response={}, error="fee_not_found",
                )
            del self._fees[account_ref][fee_id]
            return ExecutionResult(
                success=True,
                backend_reference=f"REV-{fee_id}",
                latency_ms=0.0,
                raw_response={"reversed_amount": fee.amount, "currency": fee.currency},
                error=None,
            )

        result, _replayed = self._idempotency.get_or_set(idempotency_key, do_reverse)
        return result

    def update_credit_limit(
        self, account_ref: str, new_limit: float, reason_code: str, idempotency_key: str
    ) -> ExecutionResult:
        def do_update() -> ExecutionResult:
            self._faults.maybe_delay_and_fail()
            account = self._accounts[account_ref]
            self._accounts[account_ref] = replace(account, current_limit=new_limit)
            return ExecutionResult(
                success=True,
                backend_reference=f"CLI-{account_ref}-{int(time.time() * 1000)}",
                latency_ms=0.0,
                raw_response={"new_limit": new_limit, "reason_code": reason_code},
                error=None,
            )

        result, _replayed = self._idempotency.get_or_set(idempotency_key, do_update)
        return result
