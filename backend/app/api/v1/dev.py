"""Dev-only endpoints for creating mock account data at runtime, so this
reference build isn't limited to the 3 hardcoded demo accounts in
scripts/seed_mock_data.py.

DANGER outside a reference build talking to mock adapters: this writes
directly into MockCoreBankingAdapter/MockFraudServiceAdapter's in-memory
state with zero authorization checks. That's fine here -- it's fake data
in a process-local dict, gone on restart -- but the moment this code
points at anything real, an endpoint that lets any caller fabricate
account balances/limits/statuses is a severe vulnerability, not a
convenience. Gated behind `settings.enable_dev_endpoints`; see that
field's docstring in app/config.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.conversations import get_app_state
from app.bootstrap import AppState
from app.domain.models import AccountSnapshot, AccountStatus, Address, CreditProfile, FeeRecord, RiskScore

router = APIRouter(prefix="/dev", tags=["dev-only"])


class SeedAddress(BaseModel):
    line1: str = "123 Main St"
    line2: Optional[str] = None
    city: str = "Springfield"
    state_or_province: str = "IL"
    postal_code: str = "62701"
    country: str = "US"


class SeedFee(BaseModel):
    fee_type: Literal["late_fee", "annual_fee", "foreign_transaction_fee"] = "late_fee"
    amount: float = 35.0
    currency: str = "USD"
    waivers_last_12_months: int = 0


class SeedAccountRequest(BaseModel):
    account_ref: str
    status: Literal["active", "delinquent", "charged_off", "closed"] = "active"
    current_limit: float = 5000.0
    days_past_due: int = 0
    recent_nsf_count: int = 0
    address: SeedAddress = SeedAddress()
    card_ref: Optional[str] = None
    probability_of_default: float = 0.02
    fee: Optional[SeedFee] = None


def require_dev_endpoints_enabled(state: AppState = Depends(get_app_state)) -> None:
    if not state.settings.enable_dev_endpoints:
        raise HTTPException(status_code=404, detail="dev endpoints are disabled")


@router.post("/accounts", dependencies=[Depends(require_dev_endpoints_enabled)])
def seed_account(
    body: SeedAccountRequest, state: AppState = Depends(get_app_state)
) -> dict:
    """Create (or overwrite) a mock account so you can drive any scenario
    -- clean approval, manual review, delinquent denial -- without editing
    Python. Try setting `current_limit` low with a big `fee.amount` to
    trigger manual_review, or `days_past_due` > 0 to see the delinquency
    path.
    """
    card_ref = body.card_ref or f"card_{body.account_ref}"
    address = Address(**body.address.model_dump())

    state.deps.core_banking.seed_account(AccountSnapshot(
        account_ref=body.account_ref,
        status=AccountStatus(body.status),
        current_limit=body.current_limit,
        days_past_due=body.days_past_due,
        recent_nsf_count=body.recent_nsf_count,
        address_on_file=address,
        card_ref=card_ref,
    ))
    state.deps.core_banking.seed_credit_profile(CreditProfile(
        account_ref=body.account_ref, utilization_trend=0.3, payment_history_score=0.85,
        tenure_months=24, recent_inquiries=0,
    ))
    state.deps.fraud_service.seed_risk_score(
        body.account_ref, RiskScore(probability_of_default=body.probability_of_default)
    )

    fee_id = None
    if body.fee:
        fee_id = f"fee_{body.account_ref}_{body.fee.fee_type}"
        state.deps.core_banking.seed_fee(body.account_ref, FeeRecord(
            fee_id=fee_id, fee_type=body.fee.fee_type, amount=body.fee.amount,
            currency=body.fee.currency, posted_at=datetime.now(timezone.utc),
            waivers_last_12_months=body.fee.waivers_last_12_months,
        ))

    return {
        "account_ref": body.account_ref, "card_ref": card_ref, "fee_id": fee_id,
        "note": "Start a conversation with this account_ref as customer_ref.",
    }


@router.get("/accounts/{account_ref}", dependencies=[Depends(require_dev_endpoints_enabled)])
def get_seeded_account(account_ref: str, state: AppState = Depends(get_app_state)) -> dict:
    try:
        account = state.deps.core_banking.get_account_summary(account_ref)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    fees = state.deps.core_banking.list_fees(account_ref)
    return {
        "account_ref": account.account_ref, "status": account.status.value,
        "current_limit": account.current_limit, "days_past_due": account.days_past_due,
        "card_blocked": state.deps.card_fulfillment.is_blocked(account.card_ref or ""),
        "fees": [{"fee_id": f.fee_id, "fee_type": f.fee_type, "amount": f.amount} for f in fees],
    }
