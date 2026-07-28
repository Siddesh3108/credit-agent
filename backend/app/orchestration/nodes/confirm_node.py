"""confirm_with_user node (§5.2, §15).

§15: "Any node that reaches confirm_with_user renders a distinct,
unambiguous confirmation UI... the system never executes a financial
action from an inferred 'yes' buried in free text... the confirmation
click itself is a logged event." This node pauses via interrupt() until
the frontend's ConfirmActionModal posts an explicit confirm/cancel, then
logs that click as its own audit event before returning.
"""
from __future__ import annotations

from typing import Callable

from langgraph.types import interrupt

from app.orchestration.state import ConversationState


def make_confirm_node(audit_writer) -> Callable[[ConversationState], dict]:
    def confirm_node(state: ConversationState) -> dict:
        decision = state.get("decision") or {}
        confirmation = interrupt({
            "type": "confirm_action",
            "intent": state["intent"],
            "decision_summary": {
                "outcome": decision.get("outcome"),
                "reason_codes": decision.get("reason_codes"),
            },
        })
        confirmed = bool(confirmation.get("confirmed", False))

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="human_decision",
            decision="confirmed" if confirmed else "cancelled",
            payload={"confirmation_click": True},
        )
        return {"decision": {**decision, "user_confirmed": confirmed}}

    return confirm_node
