"""Deterministic credit-limit-increase policy (source doc §7.2).

Deviation from the doc's pseudocode: guards against `account.current_limit
== 0`, which the original `(requested_limit - current_limit) / current_limit`
would divide-by-zero on. A $0 limit is a real state (e.g. a suspended
account) so this can't be assumed away; it routes to manual_review instead
of crashing the node.
"""
from __future__ import annotations

from app.domain.models import AccountSnapshot, Decision, RiskScore
from app.policy.config import PolicyConfig


def evaluate_credit_limit_increase(
    account: AccountSnapshot,
    requested_limit: float,
    risk: RiskScore,
    policy: PolicyConfig,
) -> Decision:
    if account.current_limit <= 0:
        return Decision(
            "manual_review", ["INVALID_CURRENT_LIMIT"], policy_version=policy.display_name
        )

    pct_increase = (requested_limit - account.current_limit) / account.current_limit

    if account.days_past_due > 0 or account.recent_nsf_count > 0:
        return Decision(
            "manual_review", ["DELINQUENCY_OR_NSF_FLAG"], policy_version=policy.display_name
        )

    if pct_increase > policy.auto_approval_ceiling_pct:
        return Decision(
            "manual_review", ["EXCEEDS_AUTO_APPROVAL_PCT"], policy_version=policy.display_name
        )

    if risk.probability_of_default > policy.max_pd_threshold:
        return Decision(
            "denied",
            ["RISK_SCORE_ABOVE_THRESHOLD"],
            adverse_action_required=True,
            policy_version=policy.display_name,
        )

    return Decision("approved", ["RISK_AND_POLICY_CLEARED"], policy_version=policy.display_name)
