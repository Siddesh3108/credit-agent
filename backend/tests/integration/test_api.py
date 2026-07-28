from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.models import AccountSnapshot, AccountStatus, Address, CreditProfile, FeeRecord
from app.main import create_app

ADDRESS = Address(line1="1 Main St", city="Springfield", state_or_province="IL",
                   postal_code="62701", country="US")


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The app's lifespan calls get_settings() on startup and *overwrites*
    # app.state.app_state -- building a separate AppState here and
    # assigning it before opening TestClient would just get clobbered the
    # moment the lifespan runs. Instead, point get_settings() at the test
    # DB via env var so the lifespan builds the right one itself, then
    # seed data through the instance it actually installed.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api_test.db")
    app = create_app()

    with TestClient(app) as test_client:
        deps = app.state.app_state.deps
        deps.core_banking.seed_account(AccountSnapshot(
            account_ref="acct_api_1", status=AccountStatus.ACTIVE, current_limit=5000.0,
            days_past_due=0, recent_nsf_count=0, address_on_file=ADDRESS, card_ref="card_api_1",
        ))
        deps.core_banking.seed_credit_profile(CreditProfile(
            account_ref="acct_api_1", utilization_trend=0.2, payment_history_score=0.9,
            tenure_months=36, recent_inquiries=0,
        ))
        deps.core_banking.seed_fee("acct_api_1", FeeRecord(
            fee_id="fee_api_1", fee_type="late_fee", amount=35.0, currency="USD",
            posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
        ))
        yield test_client


class TestHealthEndpoints:
    def test_health(self, client):
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestConversationFlow:
    def test_full_fee_reversal_flow_over_http(self, client):
        start = client.post("/v1/conversations", json={"customer_ref": "acct_api_1"})
        assert start.status_code == 200
        conversation_id = start.json()["conversation_id"]
        token = start.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}

        msg = client.post(
            f"/v1/conversations/{conversation_id}/messages",
            json={"message": "please waive my late fee"},
            headers=headers,
        )
        assert msg.status_code == 200
        body = msg.json()
        assert body["status"] == "awaiting_confirmation"
        assert body["decision"]["outcome"] == "approved"

        resume = client.post(
            f"/v1/conversations/{conversation_id}/resume",
            json={"kind": "confirm", "confirmed": True},
            headers=headers,
        )
        assert resume.status_code == 200
        assert resume.json()["status"] == "resolved"
        assert resume.json()["decision"]["executed"] is True

        audit = client.get(f"/v1/audit/{conversation_id}")
        assert audit.status_code == 200
        assert audit.json()["chain_intact"] is True
        assert len(audit.json()["events"]) >= 5

    def test_message_without_token_is_rejected(self, client):
        start = client.post("/v1/conversations", json={"customer_ref": "acct_api_1"})
        conversation_id = start.json()["conversation_id"]

        resp = client.post(
            f"/v1/conversations/{conversation_id}/messages", json={"message": "hello"}
        )
        assert resp.status_code == 401

    def test_message_with_wrong_conversations_token_is_rejected(self, client):
        start_a = client.post("/v1/conversations", json={"customer_ref": "acct_api_1"})
        start_b = client.post("/v1/conversations", json={"customer_ref": "acct_api_1"})
        token_a = start_a.json()["session_token"]
        conversation_id_b = start_b.json()["conversation_id"]

        resp = client.post(
            f"/v1/conversations/{conversation_id_b}/messages",
            json={"message": "hello"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 401

    def test_resume_without_a_paused_conversation_returns_conflict(self, client):
        start = client.post("/v1/conversations", json={"customer_ref": "acct_api_1"})
        conversation_id = start.json()["conversation_id"]
        token = start.json()["session_token"]

        resp = client.post(
            f"/v1/conversations/{conversation_id}/resume",
            json={"kind": "confirm", "confirmed": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409
