"""In-memory stand-in for the notification/comms system (§8.5). Real
implementation would call an email/SMS/push provider; this just records
what would have been sent, for tests and local dev to assert against."""
from __future__ import annotations

from app.domain.models import ExecutionResult


class MockNotificationAdapter:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, customer_ref: str, template: str, context: dict) -> ExecutionResult:
        record = {"customer_ref": customer_ref, "template": template, "context": context}
        self.sent.append(record)
        return ExecutionResult(
            success=True, backend_reference=f"NOTIF-{len(self.sent)}", latency_ms=0.0,
            raw_response=record, error=None,
        )
