"""audit_log node (§5.2, terminal).

Every node in this graph already writes its own audit event at the point
its decision happens, not batched at the end (§5.2's own note: "AuditLog
in the diagram is the terminal write, but classification results, policy
decisions, and escalation triggers are each logged at the point they
happen"). This node writes the one event that only makes sense at the
very end: a `conversation_turn_ended` summary tying the turn's outcome
together, useful for the FCR metric (§1.3) without having to re-derive
"how did this turn end" from scanning every prior event type.
"""
from __future__ import annotations

from typing import Callable

from app.orchestration.state import ConversationState


def make_audit_node(audit_writer) -> Callable[[ConversationState], dict]:
    def audit_node(state: ConversationState) -> dict:
        decision = state.get("decision") or {}
        if state.get("escalation_reason"):
            outcome = "escalated"
        elif decision.get("executed"):
            outcome = "resolved"
        elif decision.get("outcome") == "denied":
            outcome = "resolved"  # a clear denial communicated to the customer is still a resolution
        elif decision.get("outcome") == "clarify_info":
            outcome = "incomplete"
        elif decision.get("user_confirmed") is False:
            outcome = "abandoned"
        else:
            outcome = "incomplete"

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="conversation_turn_ended",
            payload={
                "outcome": outcome, "intent": state.get("intent"),
                "escalation_reason": state.get("escalation_reason"),
            },
        )
        return {}

    return audit_node
