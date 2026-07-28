from __future__ import annotations

from dataclasses import replace

from app.domain.models import Address
from app.policy.rules.card_replacement_rules import evaluate_card_replacement


class FakeSanctionsScreener:
    def __init__(self, sanctioned: bool = False):
        self._sanctioned = sanctioned
        self.calls: list[Address] = []

    def is_sanctioned_destination(self, address: Address) -> bool:
        self.calls.append(address)
        return self._sanctioned


def test_approves_standard_replacement_to_address_on_file(good_standing_account, policy_registry):
    policy = policy_registry.current("card_replacement")
    screener = FakeSanctionsScreener(sanctioned=False)

    decision = evaluate_card_replacement(
        good_standing_account, "damaged", good_standing_account.address_on_file, policy, screener
    )

    assert decision.outcome == "approved"
    assert decision.reason_codes == ["STANDARD_REPLACEMENT"]
    assert screener.calls  # sanctions screening still runs, even for a known address


def test_manual_review_for_new_address_without_reverification(good_standing_account, policy_registry):
    policy = policy_registry.current("card_replacement")
    screener = FakeSanctionsScreener()
    new_address = Address(
        line1="999 Other Ave", city="Metropolis", state_or_province="NY",
        postal_code="10001", country="US",
    )

    decision = evaluate_card_replacement(good_standing_account, "lost", new_address, policy, screener)

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["NEW_ADDRESS_REQUIRES_REVERIFICATION"]


def test_approves_new_address_when_reverified_this_session(good_standing_account, policy_registry):
    policy = policy_registry.current("card_replacement")
    screener = FakeSanctionsScreener()
    account = replace(good_standing_account, identity_reverified_this_session=True)
    new_address = Address(
        line1="999 Other Ave", city="Metropolis", state_or_province="NY",
        postal_code="10001", country="US",
    )

    decision = evaluate_card_replacement(account, "lost", new_address, policy, screener)

    assert decision.outcome == "approved"


def test_denies_duplicate_replacement_in_transit(good_standing_account, policy_registry):
    policy = policy_registry.current("card_replacement")
    account = replace(good_standing_account, active_replacement_in_transit=True)
    screener = FakeSanctionsScreener()

    decision = evaluate_card_replacement(
        account, "damaged", good_standing_account.address_on_file, policy, screener
    )

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["DUPLICATE_REPLACEMENT_IN_TRANSIT"]


def test_manual_review_on_sanctions_hit(good_standing_account, policy_registry):
    policy = policy_registry.current("card_replacement")
    screener = FakeSanctionsScreener(sanctioned=True)

    decision = evaluate_card_replacement(
        good_standing_account, "damaged", good_standing_account.address_on_file, policy, screener
    )

    assert decision.outcome == "manual_review"
    assert decision.reason_codes == ["OFAC_SCREENING_HIT"]


def test_address_equality_is_whitespace_and_case_insensitive(good_standing_account, policy_registry):
    """The doc's `shipping_address != account.address_on_file` check (§7.2)
    only does what it's supposed to if equivalent addresses actually
    compare equal -- see Address.__post_init__ normalization."""
    policy = policy_registry.current("card_replacement")
    screener = FakeSanctionsScreener()
    messy_same_address = Address(
        line1="  123 MAIN st  ", city="springfield", state_or_province="il",
        postal_code=" 62701 ", country="us",
    )

    decision = evaluate_card_replacement(good_standing_account, "damaged", messy_same_address, policy, screener)

    assert decision.outcome == "approved"  # not manual_review -- addresses matched
