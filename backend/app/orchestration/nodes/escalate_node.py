"""escalate_human node (§11). Builds §11.2's HandoffPackage and creates a
ticket via the ticketing adapter. Reachable from: classify_intent
(ambiguity exhausted), containment/policy_check (backend failure or
missing/ambiguous entities), and execute_action (backend failure)."""
from __future__ import annotations

from typing import Callable

from app.domain.models import Decision
from app.escalation.handoff_builder import build_handoff_package, handoff_package_to_json
from app.orchestration.state import ConversationState


def make_escalate_node(deps, audit_writer) -> Callable[[ConversationState], dict]:
    def escalate_node(state: ConversationState) -> dict:
        reason = state.get("escalation_reason") or "unspecified"
        decision_dict = state.get("decision")
        decision_obj = None
        if decision_dict:
            decision_obj = Decision(
                outcome=decision_dict.get("outcome", "manual_review"),
                reason_codes=decision_dict.get("reason_codes", []),
                adverse_action_required=decision_dict.get("adverse_action_required", False),
                policy_version=decision_dict.get("policy_version", "unversioned"),
            )

        handoff = build_handoff_package(
            ticket_id="", conversation_id=state["session_id"],
            identity_verification_level=state.get("auth_level", "unauthenticated"),
            intent=state.get("intent"), entities=state.get("entities", {}), decision=decision_obj,
            attempted_actions=[], escalation_reason=reason,
            transcript_url=f"/conversations/{state['session_id']}/transcript",
            audit_trail_url=f"/audit/{state['session_id']}",
        )
        payload = handoff_package_to_json(handoff)
        external_ref = deps.ticketing.create_ticket(payload, priority=handoff["priority"])

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="escalation_triggered",
            payload={"reason": reason, "ticket_ref": external_ref, "priority": handoff["priority"]},
        )
        return {"escalation_reason": reason}

    return escalate_node
