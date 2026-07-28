"""Mock ticketing/CRM adapter (§3's "Ticketing and CRM" component). Real
implementation would call something like Zendesk/Salesforce/ServiceNow;
this records tickets in memory so tests and local dev can assert against
what would have been created."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockTicketingAdapter:
    tickets: dict = field(default_factory=dict)
    _counter: int = 0

    def create_ticket(self, handoff_payload: dict, priority: str) -> str:
        self._counter += 1
        external_ref = f"TICKET-{self._counter:06d}"
        self.tickets[external_ref] = {"payload": handoff_payload, "priority": priority, "status": "open"}
        return external_ref

    def resolve_ticket(self, external_ref: str, note: str) -> bool:
        if external_ref not in self.tickets:
            return False
        self.tickets[external_ref]["status"] = "resolved"
        self.tickets[external_ref]["resolution_note"] = note
        return True
