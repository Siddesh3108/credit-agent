from __future__ import annotations

from dataclasses import replace

from tests.conftest import make_fee

from app.domain.models import AccountStatus
from app.policy.rules.fee_reversal_rules import evaluate_fee_reversal


def test_approves_standard_courtesy_waiver(good_standing_account, policy_registry):
    policy = policy_registry.current("fee_reversal")
    fee = make_fee(amount=35.0, waivers_last_12_months=0)

    decision = evaluate_fee_reversal(good_standing_account, fee, policy)

    assert decision.outcome == "approved"
    assert decision.reason_codes == ["STANDARD_COURTESY_WAIVER"]
    assert decision.policy_version == "fee_reversal@v3"


def test_denies_charged_off_account(good_standing_account, policy_registry):
    policy = policy_registry.current("fee_reversal")
    account = replace(good_standing_account, status=AccountStatus.CHARGED_OFF)
    fee = make_fee()

    decision = evaluate_fee_reversal(account, fee, policy)

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["ACCOUNT_NOT_ELIGIBLE"]


def test_denies_closed_account(good_standing_account, policy_registry):
    policy = policy_registry.current("fee_reversal")
    account = replace(good_standing_account, status=AccountStatus.CLOSED)

    decision = evaluate_fee_reversal(account, make_fee(), policy)

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["ACCOUNT_NOT_ELIGIBLE"]


def test_denies_when_waiver_limit_reached(good_standing_account, policy_registry):
    policy = policy_registry.current("fee_reversal")
    # config default is max_waivers_per_rolling_year = 2
    fee = make_fee(waivers_last_12_months=2)

    decision = evaluate_fee_reversal(good_standing_account, fee, policy)

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["WAIVER_LIMIT_REACHED"]


def test_manual_review_when_amount_exceeds_auto_ceiling(good_standing_account, policy_registry):
    policy = policy_registry.current("fee_reversal")
    fee = make_fee(amount=policy.auto_approval_ceiling_usd + 0.01)

    decision = evaluate_fee_reversal(good_standing_account, fee, policy)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["EXCEEDS_AUTO_CEILING"]


def test_manual_review_when_account_delinquent(good_standing_account, policy_registry):
    policy = policy_registry.current("fee_reversal")
    account = replace(good_standing_account, days_past_due=5)

    decision = evaluate_fee_reversal(account, make_fee(), policy)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["ACCOUNT_DELINQUENT"]


def test_waiver_limit_checked_before_delinquency_ceiling_order(good_standing_account, policy_registry):
    """Branch order matters for which reason_code an auditor sees first --
    lock in the doc's exact ordering (§7.2) as a regression test."""
    policy = policy_registry.current("fee_reversal")
    account = replace(good_standing_account, status=AccountStatus.CHARGED_OFF, days_past_due=10)
    fee = make_fee(waivers_last_12_months=99, amount=99999)

    decision = evaluate_fee_reversal(account, fee, policy)

    # account status is checked first in §7.2, so ACCOUNT_NOT_ELIGIBLE wins
    # even though every other condition would also fire.
    assert decision.reason_codes == ["ACCOUNT_NOT_ELIGIBLE"]
