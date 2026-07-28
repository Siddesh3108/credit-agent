from __future__ import annotations

from dataclasses import replace

from app.domain.models import RiskScore
from app.policy.rules.credit_limit_rules import evaluate_credit_limit_increase


def _risk(pd: float) -> RiskScore:
    return RiskScore(probability_of_default=pd, top_features=(("utilization", 0.4),))


def test_approves_within_ceiling_and_low_risk(good_standing_account, policy_registry):
    policy = policy_registry.current("credit_limit_increase")
    # current_limit=5000, ceiling_pct=0.25 -> up to 6250 auto-approvable
    decision = evaluate_credit_limit_increase(good_standing_account, 6000.0, _risk(0.01), policy)

    assert decision.outcome == "approved"
    assert decision.reason_codes == ["RISK_AND_POLICY_CLEARED"]


def test_manual_review_when_delinquent(good_standing_account, policy_registry):
    policy = policy_registry.current("credit_limit_increase")
    account = replace(good_standing_account, days_past_due=1)

    decision = evaluate_credit_limit_increase(account, 5500.0, _risk(0.01), policy)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["DELINQUENCY_OR_NSF_FLAG"]


def test_manual_review_when_recent_nsf(good_standing_account, policy_registry):
    policy = policy_registry.current("credit_limit_increase")
    account = replace(good_standing_account, recent_nsf_count=1)

    decision = evaluate_credit_limit_increase(account, 5500.0, _risk(0.01), policy)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["DELINQUENCY_OR_NSF_FLAG"]


def test_manual_review_when_requested_pct_exceeds_ceiling(good_standing_account, policy_registry):
    policy = policy_registry.current("credit_limit_increase")
    # 5000 -> 10000 is a 100% increase, well above the 25% ceiling
    decision = evaluate_credit_limit_increase(good_standing_account, 10000.0, _risk(0.01), policy)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["EXCEEDS_AUTO_APPROVAL_PCT"]


def test_denied_with_adverse_action_when_risk_above_threshold(good_standing_account, policy_registry):
    policy = policy_registry.current("credit_limit_increase")
    # small enough increase to clear the pct ceiling, but risk score is bad
    decision = evaluate_credit_limit_increase(good_standing_account, 5100.0, _risk(0.5), policy)

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["RISK_SCORE_ABOVE_THRESHOLD"]
    assert decision.adverse_action_required is True


def test_zero_current_limit_routes_to_manual_review_not_a_crash(good_standing_account, policy_registry):
    """Regression test for a division-by-zero the source doc's pseudocode
    did not guard against; see credit_limit_rules.py's module docstring."""
    policy = policy_registry.current("credit_limit_increase")
    account = replace(good_standing_account, current_limit=0.0)

    decision = evaluate_credit_limit_increase(account, 1000.0, _risk(0.01), policy)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["INVALID_CURRENT_LIMIT"]
