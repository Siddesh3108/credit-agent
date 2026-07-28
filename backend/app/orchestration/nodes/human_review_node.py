from __future__ import annotations

from typing import Callable

from langgraph.types import interrupt

from app.orchestration.state import ConversationState


def make_human_review_node(audit_writer) -> Callable[[ConversationState], dict]:
    def human_review_node(state: ConversationState) -> dict:
        decision = state.get("decision") or {}
        human_input = interrupt({
            "type": "human_decision",
            "intent": state.get("intent"),
            "decision_summary": {
                "outcome": decision.get("outcome"),
                "reason_codes": decision.get("reason_codes", []),
            },
            "review_note": "Approve or deny this customer request.",
        })

        resumed_outcome = human_input.get("outcome", "denied")
        audit_writer.append(
            session_id=state["session_id"],
            actor=f"human:{human_input.get('agent_id', 'unknown')}",
            event_type="human_decision",
            decision=resumed_outcome,
            payload={"note": human_input.get("note", "")},
        )

        return {"decision": {**decision, "outcome": resumed_outcome}}

    return human_review_node
