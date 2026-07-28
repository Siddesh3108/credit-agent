"""containment_node (§6.3, §10.7).

Blocking a reported-stolen card is unconditional and happens before
policy evaluation, user confirmation, or even successful classification
of the rest of the message -- it does not wait on anything else the
conversation is doing. This node runs immediately after intent routing
and is a no-op for every intent/reason except card_replacement + stolen.
"""
from __future__ import annotations

from typing import Callable

from app.core.idempotency import make_idempotency_key
from app.orchestration.state import ConversationState


def make_containment_node(deps, audit_writer) -> Callable[[ConversationState], dict]:
    def containment_node(state: ConversationState) -> dict:
        if state.get("intent") != "card_replacement":
            return {}
        if not isinstance(state.get("entities"), dict):
            return {}
        if state.get("entities", {}).get("reason") != "stolen":
            return {}

        account_ref = state["customer_ref"]
        try:
            account = deps.core_banking.get_account_summary(account_ref)
        except Exception:
            return {"escalation_reason": "backend_failure"}

        card_ref = account.card_ref or account_ref
        idem_key = make_idempotency_key(state["session_id"], "containment", card_ref)

        result = deps.card_replacement_saga.contain_if_stolen(card_ref, "stolen", idem_key)

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="action_executed",
            payload={"action": "block_card", "unconditional": True, "result": result},
        )
        return {}

    return containment_node
