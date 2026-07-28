"""Deterministic card-replacement policy (source doc §7.2).

Deviation from the doc's pseudocode: `is_sanctioned_destination` is
injected as a `SanctionsScreener` collaborator rather than called as a
bare free function, so a contract test can swap in a fake screener without
monkeypatching a module-level function. Production wires this to
`integrations/fraud_service_adapter.py`, which is where a real OFAC/
sanctions vendor call belongs (see that file's module docstring for why
no real sanctioned-country list ships in this repo).
"""
from __future__ import annotations

from typing import Protocol

from app.domain.models import AccountSnapshot, Address, Decision
from app.policy.config import PolicyConfig


class SanctionsScreener(Protocol):
    def is_sanctioned_destination(self, address: Address) -> bool: ...


def evaluate_card_replacement(
    account: AccountSnapshot,
    reason: str,
    shipping_address: Address,
    policy: PolicyConfig,
    sanctions_screener: SanctionsScreener,
) -> Decision:
    if (
        shipping_address != account.address_on_file
        and not account.identity_reverified_this_session
    ):
        return Decision(
            "manual_review",
            ["NEW_ADDRESS_REQUIRES_REVERIFICATION"],
            policy_version=policy.display_name,
        )

    if account.active_replacement_in_transit:
        return Decision(
            "denied", ["DUPLICATE_REPLACEMENT_IN_TRANSIT"], policy_version=policy.display_name
        )

    if sanctions_screener.is_sanctioned_destination(shipping_address):
        return Decision(
            "manual_review", ["OFAC_SCREENING_HIT"], policy_version=policy.display_name
        )

    return Decision("approved", ["STANDARD_REPLACEMENT"], policy_version=policy.display_name)
