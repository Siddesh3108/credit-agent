"""execute_action node (§5.2).

Only reached after policy_check produced "approved" (directly, or via a
human's manual_review override) and confirm_with_user's UI confirmation
click. Every write carries an idempotency key derived from
(session_id, node_name, ...) per §8.2, so interrupt()'s "re-run the node
from the top on resume" (§5.4) can never cause a duplicate fee reversal,
double credit line update, or a second shipment.
"""
from __future__ import annotations

from typing import Callable

from app.core.idempotency import make_idempotency_key
from app.domain.models import Address
from app.orchestration.state import ConversationState


def make_execute_action_node(deps, audit_writer) -> Callable[[ConversationState], dict]:
    def execute_action_node(state: ConversationState) -> dict:
        intent = state["intent"]
        decision = state.get("decision") or {}
        account_ref = state["customer_ref"]
        idem_key = make_idempotency_key(state["session_id"], "execute_action", intent or "unknown")

        try:
            if intent == "fee_reversal":
                result = deps.core_banking.reverse_fee(account_ref, decision["fee_id"], idem_key)

            elif intent == "credit_limit_increase":
                result = deps.core_banking.update_credit_limit(
                    account_ref, decision["requested_limit"],
                    ",".join(decision.get("reason_codes", [])), idem_key,
                )

            elif intent == "card_replacement":
                addr = decision.get("shipping_address") or {}
                shipping_address = Address(**addr)
                saga_result = deps.card_replacement_saga.ship(
                    account_ref=account_ref, reason=decision["reason"],
                    shipping_address=shipping_address, ship_idempotency_key=idem_key,
                )
                if saga_result.status != "completed":
                    audit_writer.append(
                        session_id=state["session_id"], actor="system", event_type="action_failed",
                        payload={"intent": intent, "saga_status": saga_result.status},
                    )
                    return {"escalation_reason": "backend_failure"}
                result = saga_result.fulfillment_result

            else:
                return {"escalation_reason": "unknown_intent"}

        except Exception as exc:  # noqa: BLE001 -- backend call failed outright
            audit_writer.append(
                session_id=state["session_id"], actor="system", event_type="action_failed",
                payload={"intent": intent, "error": str(exc)},
            )
            return {"escalation_reason": "backend_failure"}

        if not result.get("success", True):
            audit_writer.append(
                session_id=state["session_id"], actor="system", event_type="action_failed",
                payload={"intent": intent, "result": dict(result)},
            )
            return {"escalation_reason": "backend_failure"}

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="action_executed",
            payload={"intent": intent, "result": dict(result)},
        )
        return {"decision": {**decision, "executed": True, "execution_result": dict(result)}}

    return execute_action_node
