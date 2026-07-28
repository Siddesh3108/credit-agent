"""Deterministic fee-reversal policy (source doc §7.2).

Every branch emits a reason_code that flows straight into the audit event,
so any decision can be explained by looking up one code rather than
re-reading a transcript.
"""
from __future__ import annotations

from app.domain.models import AccountSnapshot, AccountStatus, Decision, FeeRecord
from app.policy.config import PolicyConfig


def evaluate_fee_reversal(
    account: AccountSnapshot, fee: FeeRecord, policy: PolicyConfig
) -> Decision:
    if account.status in (AccountStatus.CHARGED_OFF, AccountStatus.CLOSED):
        return Decision("denied", ["ACCOUNT_NOT_ELIGIBLE"], policy_version=policy.display_name)

    if fee.waivers_last_12_months >= policy.max_waivers_per_rolling_year:
        return Decision("denied", ["WAIVER_LIMIT_REACHED"], policy_version=policy.display_name)

    if fee.amount > policy.auto_approval_ceiling_usd:
        return Decision("manual_review", ["EXCEEDS_AUTO_CEILING"], policy_version=policy.display_name)

    if account.days_past_due > 0:
        return Decision("manual_review", ["ACCOUNT_DELINQUENT"], policy_version=policy.display_name)

    return Decision("approved", ["STANDARD_COURTESY_WAIVER"], policy_version=policy.display_name)
