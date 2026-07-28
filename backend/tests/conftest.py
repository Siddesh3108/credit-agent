from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.domain.models import (
    AccountSnapshot,
    AccountStatus,
    Address,
)
from app.policy.config import PolicyRegistry

BACKEND_ROOT = Path(__file__).resolve().parents[1]
POLICY_CONFIG_DIR = BACKEND_ROOT / "app" / "policy" / "config_versions"


@pytest.fixture
def policy_registry() -> PolicyRegistry:
    return PolicyRegistry.from_directory(POLICY_CONFIG_DIR)


@pytest.fixture
def sample_address() -> Address:
    return Address(
        line1="123 Main St",
        line2=None,
        city="Springfield",
        state_or_province="IL",
        postal_code="62701",
        country="US",
    )


@pytest.fixture
def good_standing_account(sample_address: Address) -> AccountSnapshot:
    return AccountSnapshot(
        account_ref="acct_001",
        status=AccountStatus.ACTIVE,
        current_limit=5000.0,
        days_past_due=0,
        recent_nsf_count=0,
        address_on_file=sample_address,
        active_replacement_in_transit=False,
        identity_reverified_this_session=False,
    )


def make_fee(**overrides):
    from app.domain.models import FeeRecord

    defaults = dict(
        fee_id="fee_001",
        fee_type="late_fee",
        amount=35.0,
        currency="USD",
        posted_at=datetime.now(timezone.utc) - timedelta(days=1),
        waivers_last_12_months=0,
    )
    defaults.update(overrides)
    return FeeRecord(**defaults)
