"""policy_check node (§5.4, transcribed close to verbatim).

Scope simplification versus §6's per-intent subgraphs: the doc describes
each intent as its own LangGraph subgraph with named sub-states
(identify_fee -> verify_eligibility -> policy_check for fee reversal;
gather_requested_amount -> soft_pull_consent -> risk_check -> policy_check
for credit limit; identify_reason -> containment_action ->
identity_reverification -> sanctions_screening -> policy_check for card
replacement). This reference implementation folds each flow's data-
gathering into this one node (dispatched by intent) rather than building
three separate mounted subgraphs with their own checkpointed sub-states.
Behaviorally equivalent for what's tested here; splitting into real
subgraphs is a mechanical refactor if you need to checkpoint/resume
*inside* a flow (e.g. resuming specifically mid-fee-selection) rather than
only at this node's boundary.

Card replacement's containment_action is the one sub-state NOT folded in
here -- §6.3 is explicit that blocking a reported-stolen card is
unconditional and independent of policy evaluation, so it runs from
route_node.py before this node is ever reached, not from inside it.

Every branch's `interrupt()` payload includes the handoff package so a
human reviewing a paused session has everything in one read (§11.2),
matching §5.4's `policy_check_node` example almost exactly -- the main
addition is the per-intent data gathering the doc's snippet abstracts
away with `state["intent"], state["entities"]`.
"""
from __future__ import annotations

from typing import Callable

from langgraph.types import interrupt

from app.core.idempotency import make_idempotency_key
from app.domain.models import Address
from app.escalation.handoff_builder import build_handoff_package, handoff_package_to_json
from app.orchestration.state import ConversationState


def make_policy_check_node(deps, audit_writer) -> Callable[[ConversationState], dict]:
    def policy_check_node(state: ConversationState) -> dict:
        intent = state["intent"]
        entities = state.get("entities", {})
        account_ref = state["customer_ref"]  # 1:1 customer:account simplification -- see README

        try:
            account = deps.core_banking.get_account_summary(account_ref)
        except Exception:
            return {"escalation_reason": "backend_failure"}

        if intent == "fee_reversal":
            matching_fees = [
                f for f in deps.core_banking.list_fees(account_ref)
                if entities.get("fee_type") is None or f.fee_type == entities["fee_type"]
            ]
            if len(matching_fees) != 1:
                return {"decision": {"outcome": "clarify_info", "clarification_message": "Which fee would you like to reverse? For example, the late fee from last week."}}
            fee = matching_fees[0]
            decision = deps.policy_engine.evaluate_fee_reversal(account, fee)
            gathered = {"fee_id": fee.fee_id, "fee_amount": fee.amount, "fee_currency": fee.currency}

        elif intent == "credit_limit_increase":
            requested_limit = entities.get("requested_limit") or entities.get("amount") or entities.get("credit_limit")
            if requested_limit is None:
                return {"decision": {"outcome": "clarify_info", "clarification_message": "How much would you like to increase your credit limit to?"}}
            try:
                requested_limit = float(str(requested_limit).replace(",", ""))
            except ValueError:
                return {"decision": {"outcome": "clarify_info", "clarification_message": "How much would you like to increase your credit limit to?"}}
            try:
                risk = deps.fraud_service.score_risk(account_ref)
            except Exception:
                return {"escalation_reason": "backend_failure"}
            decision = deps.policy_engine.evaluate_credit_limit_increase(account, requested_limit, risk)
            gathered = {"requested_limit": requested_limit, "risk_pd": risk.probability_of_default}

        elif intent == "card_replacement":
            reason = entities.get("reason")
            if reason is None:
                return {"decision": {"outcome": "clarify_info", "clarification_message": "To process a card replacement, I also need the reason. Is the card lost, stolen, or damaged?"}}
            addr = entities.get("shipping_address")
            shipping_address = Address(**addr) if addr else account.address_on_file
            decision = deps.policy_engine.evaluate_card_replacement(account, reason, shipping_address)
            gathered = {
                "reason": reason,
                "shipping_address": shipping_address.__dict__,
                "card_ref": account.card_ref,
            }
        elif intent == "general_inquiry":
            decision_dict = {"outcome": "clarify_info", "clarification_message": "I'm your card servicing agent. For general inquiries like branch hours or locations, please check our main website or let me know if you need help with your card!"}
            return {"decision": decision_dict}
        else:
            return {"escalation_reason": "unknown_intent"}

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="policy_decision",
            decision=decision.outcome, reason_codes=decision.reason_codes,
            payload={"policy_version": decision.policy_version, **gathered},
        )

        if decision.outcome == "manual_review":
            handoff = build_handoff_package(
                ticket_id="", conversation_id=state["session_id"],
                identity_verification_level=state["auth_level"], intent=intent, entities=entities,
                decision=decision, attempted_actions=[], escalation_reason="manual_review",
                transcript_url=f"/conversations/{state['session_id']}/transcript",
                audit_trail_url=f"/audit/{state['session_id']}",
            )
            human_input = interrupt({
                "reason": decision.reason_codes,
                "handoff_package": handoff_package_to_json(handoff),
            })
            # On resume, human_input is whatever the human agent's console
            # sent via Command(resume=...) -- expected shape:
            # {"outcome": "approved"|"denied", "note": str}. A human
            # approving a manual_review case overrides the outcome but the
            # reason codes and gathered data are preserved for the audit
            # trail's record of what was actually reviewed.
            resumed_outcome = human_input.get("outcome", "denied")
            audit_writer.append(
                session_id=state["session_id"], actor=f"human:{human_input.get('agent_id', 'unknown')}",
                event_type="human_decision", decision=resumed_outcome,
                payload={"note": human_input.get("note", "")},
            )
            return {"decision": {**decision.dict(), "outcome": resumed_outcome, **gathered}}

        return {"decision": {**decision.dict(), **gathered}}

    return policy_check_node
