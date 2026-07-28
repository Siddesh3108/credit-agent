from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/dev_endpoint_test.db")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


class TestDevSeedAccount:
    def test_seed_and_use_a_dynamic_account_end_to_end(self, client):
        seed_resp = client.post("/v1/dev/accounts", json={
            "account_ref": "dyn_acct_1",
            "current_limit": 5000.0,
            "fee": {"fee_type": "late_fee", "amount": 35.0},
        })
        assert seed_resp.status_code == 200

        get_resp = client.get("/v1/dev/accounts/dyn_acct_1")
        assert get_resp.status_code == 200
        assert get_resp.json()["fees"][0]["fee_type"] == "late_fee"

        start = client.post("/v1/conversations", json={"customer_ref": "dyn_acct_1"})
        token = start.json()["session_token"]
        conv_id = start.json()["conversation_id"]

        msg = client.post(
            f"/v1/conversations/{conv_id}/messages",
            json={"message": "please waive my late fee"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert msg.status_code == 200
        assert msg.json()["decision"]["outcome"] == "approved"

    def test_seed_account_that_triggers_manual_review(self, client):
        client.post("/v1/dev/accounts", json={
            "account_ref": "dyn_acct_review",
            "current_limit": 3000.0,
            "fee": {"fee_type": "annual_fee", "amount": 500.0},  # well above the auto ceiling
        })
        start = client.post("/v1/conversations", json={"customer_ref": "dyn_acct_review"})
        token = start.json()["session_token"]
        conv_id = start.json()["conversation_id"]

        msg = client.post(
            f"/v1/conversations/{conv_id}/messages",
            json={"message": "can you dispute this annual fee"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert msg.json()["status"] == "awaiting_human_review"

    def test_dev_endpoints_can_be_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/disabled_test.db")
        monkeypatch.setenv("ENABLE_DEV_ENDPOINTS", "false")
        app = create_app()
        with TestClient(app) as c:
            resp = c.post("/v1/dev/accounts", json={"account_ref": "x"})
            assert resp.status_code == 404
