"""Load test scaffold (§12.1's latency SLOs). Not run in this build --
requires `pip install locust` and a live server to point at.

Usage: locust -f evaluation/load_test/locustfile.py --host http://localhost:8000
"""
from locust import HttpUser, task, between


class ServicingAgentUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        resp = self.client.post("/v1/conversations", json={"customer_ref": "acct_001"})
        data = resp.json()
        self.conversation_id = data["conversation_id"]
        self.headers = {"Authorization": f"Bearer {data['session_token']}"}

    @task
    def fee_reversal_turn(self):
        self.client.post(
            f"/v1/conversations/{self.conversation_id}/messages",
            json={"message": "please waive my late fee"},
            headers=self.headers,
        )
