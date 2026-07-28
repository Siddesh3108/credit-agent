"""Shared domain types used across policy, integrations, and orchestration.

The source design doc references these types (AccountSnapshot, FeeRecord,
Address, CreditProfile/RiskScore, ExecutionResult, Decision) inline in
pseudocode (§7.2, §8.1) without pinning them to a file. Centralizing them
here avoids a circular import between `policy` (which evaluates them) and
`integrations` (which produces them).

Design note -- Decision as a dataclass, not a literal TypedDict:
The doc defines `Decision` as a TypedDict in §7.4, but §7.2's pseudocode
constructs it positionally: `Decision("denied", ["ACCOUNT_NOT_ELIGIBLE"])`
and `Decision("denied", [...], adverse_action_required=True)`. A plain
TypedDict does not support positional/keyword constructor calls like that
-- only a dataclass (or regular class) does. This implementation uses a
frozen dataclass, which supports both the §7.2 constructor calls verbatim
and the §7.4 field contract (via `.dict()` for JSON/audit serialization).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from typing_extensions import TypedDict


class AccountStatus(str, Enum):
    ACTIVE = "active"
    DELINQUENT = "delinquent"
    CHARGED_OFF = "charged_off"
    CLOSED = "closed"


@dataclass(frozen=True)
class Address:
    """Normalizes on construction (trim + case-fold) so two addresses that
    only differ in whitespace/casing compare equal via the dataclass's
    auto-generated __eq__/__hash__ -- see §17-A's "new address requires
    reverification" check, which depends on this comparison being robust.
    """

    line1: str
    city: str
    state_or_province: str
    postal_code: str
    country: str  # ISO 3166-1 alpha-2
    line2: Optional[str] = None

    def __post_init__(self) -> None:
        # All fields normalized the same way (strip + uppercase) so equality
        # comparison is consistently case/whitespace-insensitive. A caught
        # test failure here: normalizing state/postal/country but leaving
        # line1/city in original case meant "123 Main St" != "123 MAIN ST"
        # -- silently defeating the §7.2 "is this the address on file"
        # check for any address entered in different casing.
        object.__setattr__(self, "line1", self.line1.strip().upper())
        object.__setattr__(self, "line2", ((self.line2 or "").strip().upper() or None))
        object.__setattr__(self, "city", self.city.strip().upper())
        object.__setattr__(self, "state_or_province", self.state_or_province.strip().upper())
        object.__setattr__(self, "postal_code", self.postal_code.strip().upper())
        object.__setattr__(self, "country", self.country.strip().upper())


@dataclass(frozen=True)
class AccountSnapshot:
    account_ref: str
    status: AccountStatus
    current_limit: float
    days_past_due: int
    recent_nsf_count: int
    address_on_file: Address
    active_replacement_in_transit: bool = False
    identity_reverified_this_session: bool = False
    card_ref: Optional[str] = None
    authorized_user: bool = False


@dataclass(frozen=True)
class FeeRecord:
    fee_id: str
    fee_type: Literal["late_fee", "annual_fee", "foreign_transaction_fee"]
    amount: float
    currency: str
    posted_at: datetime
    waivers_last_12_months: int


@dataclass(frozen=True)
class CreditProfile:
    account_ref: str
    utilization_trend: float
    payment_history_score: float
    tenure_months: int
    recent_inquiries: int


@dataclass(frozen=True)
class RiskScore:
    probability_of_default: float
    top_features: tuple = field(default_factory=tuple)
    model_version: str = "unversioned"


class ExecutionResult(TypedDict):
    success: bool
    backend_reference: str
    latency_ms: float
    raw_response: dict
    error: Optional[str]


DecisionOutcome = Literal["approved", "denied", "manual_review"]


@dataclass(frozen=True)
class Decision:
    outcome: DecisionOutcome
    reason_codes: list
    adverse_action_required: bool = False
    policy_version: str = "unversioned"
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reason_codes": list(self.reason_codes),
            "adverse_action_required": self.adverse_action_required,
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at,
        }
