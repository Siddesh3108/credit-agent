"""Contract tests (§16.1): every adapter implementation -- mock or real --
is exercised against the same behavioral expectations, so "the mock passes
its tests" actually means something about what a real adapter must also
satisfy. Only mocks exist in this repo; a real adapter added later plugs
into the same `ADAPTER_FACTORIES` list and inherits every test below for
free.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models import AccountSnapshot, AccountStatus, Address, CreditProfile, FeeRecord
from app.integrations.mocks.mock_card_fulfillment import MockCardFulfillmentAdapter
from app.integrations.mocks.mock_core_banking import MockCoreBankingAdapter, UnknownAccountError

ADDRESS = Address(line1="1 Main St", city="Springfield", state_or_province="IL",
                   postal_code="62701", country="US")


def _seeded_core_banking() -> MockCoreBankingAdapter:
    adapter = MockCoreBankingAdapter()
    adapter.seed_account(AccountSnapshot(
        account_ref="acct_contract_1", status=AccountStatus.ACTIVE, current_limit=5000.0,
        days_past_due=0, recent_nsf_count=0, address_on_file=ADDRESS,
    ))
    adapter.seed_credit_profile(CreditProfile(
        account_ref="acct_contract_1", utilization_trend=0.3, payment_history_score=0.9,
        tenure_months=24, recent_inquiries=1,
    ))
    adapter.seed_fee("acct_contract_1", FeeRecord(
        fee_id="fee_contract_1", fee_type="late_fee", amount=35.0, currency="USD",
        posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
    ))
    return adapter


CORE_BANKING_FACTORIES = [_seeded_core_banking]
CARD_FULFILLMENT_FACTORIES = [MockCardFulfillmentAdapter]


@pytest.mark.parametrize("make_adapter", CORE_BANKING_FACTORIES)
class TestCoreBankingAdapterContract:
    def test_get_account_summary_returns_snapshot(self, make_adapter):
        adapter = make_adapter()
        account = adapter.get_account_summary("acct_contract_1")
        assert account.account_ref == "acct_contract_1"

    def test_get_account_summary_unknown_account_raises(self, make_adapter):
        adapter = make_adapter()
        with pytest.raises((KeyError, UnknownAccountError)):
            adapter.get_account_summary("does_not_exist")

    def test_reverse_fee_is_idempotent(self, make_adapter):
        adapter = make_adapter()
        r1 = adapter.reverse_fee("acct_contract_1", "fee_contract_1", idempotency_key="idem-1")
        r2 = adapter.reverse_fee("acct_contract_1", "fee_contract_1", idempotency_key="idem-1")
        assert r1["success"] is True
        assert r1 == r2  # replay returns the identical result, not a second effect

    def test_reverse_fee_unknown_fee_fails_gracefully(self, make_adapter):
        adapter = make_adapter()
        result = adapter.reverse_fee("acct_contract_1", "no_such_fee", idempotency_key="idem-x")
        assert result["success"] is False
        assert result["error"] == "fee_not_found"

    def test_update_credit_limit_is_idempotent(self, make_adapter):
        adapter = make_adapter()
        r1 = adapter.update_credit_limit("acct_contract_1", 6000.0, "RISK_AND_POLICY_CLEARED", "idem-2")
        r2 = adapter.update_credit_limit("acct_contract_1", 6000.0, "RISK_AND_POLICY_CLEARED", "idem-2")
        assert r1 == r2
        account = adapter.get_account_summary("acct_contract_1")
        assert account.current_limit == 6000.0

    def test_different_idempotency_keys_are_independent_operations(self, make_adapter):
        adapter = make_adapter()
        adapter.update_credit_limit("acct_contract_1", 6000.0, "X", "idem-a")
        adapter.update_credit_limit("acct_contract_1", 7000.0, "X", "idem-b")
        account = adapter.get_account_summary("acct_contract_1")
        assert account.current_limit == 7000.0  # second call's effect won, not blocked as a "replay"


@pytest.mark.parametrize("make_adapter", CARD_FULFILLMENT_FACTORIES)
class TestCardFulfillmentAdapterContract:
    def test_block_card_is_idempotent(self, make_adapter):
        adapter = make_adapter()
        r1 = adapter.block_card("card_1", "stolen", idempotency_key="blk-1")
        r2 = adapter.block_card("card_1", "stolen", idempotency_key="blk-1")
        assert r1 == r2
        assert adapter.is_blocked("card_1")

    def test_order_replacement_is_idempotent(self, make_adapter):
        adapter = make_adapter()
        r1 = adapter.order_replacement("acct_1", "damaged", ADDRESS, False, idempotency_key="ship-1")
        r2 = adapter.order_replacement("acct_1", "damaged", ADDRESS, False, idempotency_key="ship-1")
        assert r1 == r2
        assert len(adapter.shipments_for("acct_1")) == 1  # not two shipments from the replay

    def test_expedited_shipment_has_shorter_eta(self, make_adapter):
        adapter = make_adapter()
        standard = adapter.order_replacement("acct_1", "damaged", ADDRESS, False, idempotency_key="s1")
        expedited = adapter.order_replacement("acct_2", "lost", ADDRESS, True, idempotency_key="s2")
        assert expedited["raw_response"]["eta_days"] < standard["raw_response"]["eta_days"]
