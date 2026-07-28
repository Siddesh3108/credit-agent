"""Seeds the mock backends with demo accounts so `uvicorn app.main:app`
has something to talk to immediately (§14's scripts/seed_mock_data.py).

This seeds an in-process AppState and is meant to be imported by a dev
script or adapted into an app-startup hook -- the mock adapters are
in-memory, so seeding only has effect within the same Python process
that serves requests. For `uvicorn app.main:app` specifically, see
docs/RUNBOOK.md for wiring this into the lifespan for local dev.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap import build_app_state
from app.config import Settings
from app.domain.models import (
    AccountSnapshot,
    AccountStatus,
    Address,
    CreditProfile,
    FeeRecord,
    RiskScore,
)

DEMO_ADDRESS = Address(
    line1="742 Evergreen Terrace", city="Springfield", state_or_province="IL",
    postal_code="62704", country="US",
)


def seed(app_state) -> None:
    deps = app_state.deps

    # A clean-standing account for the "everything auto-approves" demo path.
    deps.core_banking.seed_account(AccountSnapshot(
        account_ref="acct_001", status=AccountStatus.ACTIVE, current_limit=5000.0,
        days_past_due=0, recent_nsf_count=0, address_on_file=DEMO_ADDRESS, card_ref="card_001",
    ))
    deps.core_banking.seed_credit_profile(CreditProfile(
        account_ref="acct_001", utilization_trend=0.25, payment_history_score=0.92,
        tenure_months=48, recent_inquiries=0,
    ))
    deps.core_banking.seed_fee("acct_001", FeeRecord(
        fee_id="fee_001", fee_type="late_fee", amount=35.0, currency="USD",
        posted_at=datetime.now(timezone.utc) - timedelta(days=2), waivers_last_12_months=0,
    ))
    deps.fraud_service.seed_risk_score("acct_001", RiskScore(probability_of_default=0.02))

    # An account that will land in manual_review (fee above the auto ceiling).
    policy = deps.policy_engine._registry.current("fee_reversal")  # noqa: SLF001
    deps.core_banking.seed_account(AccountSnapshot(
        account_ref="acct_002", status=AccountStatus.ACTIVE, current_limit=3000.0,
        days_past_due=0, recent_nsf_count=0, address_on_file=DEMO_ADDRESS, card_ref="card_002",
    ))
    deps.core_banking.seed_credit_profile(CreditProfile(
        account_ref="acct_002", utilization_trend=0.4, payment_history_score=0.8,
        tenure_months=12, recent_inquiries=1,
    ))
    deps.core_banking.seed_fee("acct_002", FeeRecord(
        fee_id="fee_002", fee_type="annual_fee", amount=policy.auto_approval_ceiling_usd + 25,
        currency="USD", posted_at=datetime.now(timezone.utc) - timedelta(days=1),
        waivers_last_12_months=0,
    ))
    deps.fraud_service.seed_risk_score("acct_002", RiskScore(probability_of_default=0.03))

    # A delinquent account -- fee reversal and credit limit both route to
    # manual_review regardless of amount (§17's edge case catalogue, B/C).
    deps.core_banking.seed_account(AccountSnapshot(
        account_ref="acct_003", status=AccountStatus.ACTIVE, current_limit=2000.0,
        days_past_due=15, recent_nsf_count=1, address_on_file=DEMO_ADDRESS, card_ref="card_003",
    ))
    deps.core_banking.seed_credit_profile(CreditProfile(
        account_ref="acct_003", utilization_trend=0.6, payment_history_score=0.5,
        tenure_months=6, recent_inquiries=3,
    ))
    deps.core_banking.seed_fee("acct_003", FeeRecord(
        fee_id="fee_003", fee_type="late_fee", amount=35.0, currency="USD",
        posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
    ))

    print("Seeded 3 demo accounts: acct_001 (clean), acct_002 (manual review), acct_003 (delinquent)")


if __name__ == "__main__":
    settings = Settings()
    state = build_app_state(settings)
    seed(state)
