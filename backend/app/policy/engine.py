"""The Policy and Risk Decision Engine (§7).

This is the component the design doc says a regulator, auditor, or
security review will scrutinize hardest (§7.1). It is deterministic given
the same inputs, independently unit-testable, versioned, and explainable
per-decision. It has no visibility into "what the model felt like doing"
-- only structured inputs sourced from system-of-record data via the
adapters in `app/integrations`.

Principle 1 (§2) in code: nothing in this module imports from
`app.nlu` or `app.orchestration`, and nothing here ever reads
conversation text. If a future change makes that import graph untrue,
that is a Principle 1 violation, not a refactor.
"""
from __future__ import annotations

from app.domain.models import AccountSnapshot, Address, Decision, FeeRecord, RiskScore
from app.policy.config import PolicyRegistry
from app.policy.rules.card_replacement_rules import SanctionsScreener, evaluate_card_replacement
from app.policy.rules.credit_limit_rules import evaluate_credit_limit_increase
from app.policy.rules.fee_reversal_rules import evaluate_fee_reversal


class PolicyEngine:
    def __init__(self, registry: PolicyRegistry, sanctions_screener: SanctionsScreener):
        self._registry = registry
        self._sanctions_screener = sanctions_screener

    def evaluate_fee_reversal(self, account: AccountSnapshot, fee: FeeRecord) -> Decision:
        policy = self._registry.current("fee_reversal")
        return evaluate_fee_reversal(account, fee, policy)

    def evaluate_credit_limit_increase(
        self, account: AccountSnapshot, requested_limit: float, risk: RiskScore
    ) -> Decision:
        policy = self._registry.current("credit_limit_increase")
        return evaluate_credit_limit_increase(account, requested_limit, risk, policy)

    def evaluate_card_replacement(
        self, account: AccountSnapshot, reason: str, shipping_address: Address
    ) -> Decision:
        policy = self._registry.current("card_replacement")
        return evaluate_card_replacement(
            account, reason, shipping_address, policy, self._sanctions_screener
        )
