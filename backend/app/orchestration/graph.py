"""Assembles the top-level StateGraph per §5.2/§5.3.

Topology (see module docstrings on individual nodes for the scope
simplifications versus §6's three per-intent subgraphs):

    START -> authenticate -> classify_intent
    classify_intent --[clarify]--> classify_intent (loops, capped at
        MAX_CLARIFICATION_ATTEMPTS inside NLUPipeline itself)
    classify_intent --[escalate]--> escalate_human
    classify_intent --[route]--> containment -> policy_check
    policy_check --[approved]--> confirm_with_user
    policy_check --[denied]--> audit_log   (bot informs customer directly)
    policy_check --[escalate]--> escalate_human
    confirm_with_user --[confirmed]--> execute_action
    confirm_with_user --[cancelled]--> audit_log
    execute_action --[success]--> audit_log
    execute_action --[escalate]--> escalate_human
    escalate_human -> audit_log -> END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.audit_node import make_audit_node
from app.orchestration.nodes.authenticate_node import make_authenticate_node
from app.orchestration.nodes.classify_intent_node import make_classify_intent_node
from app.orchestration.nodes.confirm_node import make_confirm_node
from app.orchestration.nodes.containment_node import make_containment_node
from app.orchestration.nodes.escalate_node import make_escalate_node
from app.orchestration.nodes.execute_action_node import make_execute_action_node
from app.orchestration.nodes.route_node import make_policy_check_node
from app.orchestration.state import ConversationState


def build_graph(deps, audit_writer, checkpointer):
    builder = StateGraph(ConversationState)

    builder.add_node("authenticate", make_authenticate_node(audit_writer))
    builder.add_node("classify_intent", make_classify_intent_node(deps.nlu, audit_writer))
    builder.add_node("containment", make_containment_node(deps, audit_writer))
    builder.add_node("policy_check", make_policy_check_node(deps, audit_writer))
    builder.add_node("confirm_with_user", make_confirm_node(audit_writer))
    builder.add_node("execute_action", make_execute_action_node(deps, audit_writer))
    builder.add_node("escalate_human", make_escalate_node(deps, audit_writer))
    builder.add_node("audit_log", make_audit_node(audit_writer))

    builder.add_edge(START, "authenticate")

    def route_after_auth(state: ConversationState) -> str:
        return "escalate" if state.get("escalation_reason") else "classify"

    builder.add_conditional_edges(
        "authenticate", route_after_auth, {"classify": "classify_intent", "escalate": "escalate_human"}
    )

    def route_after_classify(state: ConversationState) -> str:
        if state.get("escalation_reason"):
            return "escalate"
        if state.get("intent"):
            return "route"
        return "clarify"

    builder.add_conditional_edges(
        "classify_intent", route_after_classify,
        {"clarify": "classify_intent", "route": "containment", "escalate": "escalate_human"},
    )

    def route_after_containment(state: ConversationState) -> str:
        return "escalate" if state.get("escalation_reason") else "check"

    builder.add_conditional_edges(
        "containment", route_after_containment, {"check": "policy_check", "escalate": "escalate_human"}
    )

    def route_after_policy_check(state: ConversationState) -> str:
        if state.get("escalation_reason"):
            return "escalate"
        outcome = (state.get("decision") or {}).get("outcome")
        if outcome == "approved":
            return "confirm"
        if outcome == "denied" or outcome == "clarify_info":
            return "audit"
        return "escalate"  # manual_review that somehow reached here unresolved -- fail safe

    builder.add_conditional_edges(
        "policy_check", route_after_policy_check,
        {"confirm": "confirm_with_user", "audit": "audit_log", "escalate": "escalate_human"},
    )

    def route_after_confirm(state: ConversationState) -> str:
        return "execute" if (state.get("decision") or {}).get("user_confirmed") else "audit"

    builder.add_conditional_edges(
        "confirm_with_user", route_after_confirm, {"execute": "execute_action", "audit": "audit_log"}
    )

    def route_after_execute(state: ConversationState) -> str:
        return "escalate" if state.get("escalation_reason") else "audit"

    builder.add_conditional_edges(
        "execute_action", route_after_execute, {"audit": "audit_log", "escalate": "escalate_human"}
    )

    builder.add_edge("escalate_human", "audit_log")
    builder.add_edge("audit_log", END)

    return builder.compile(checkpointer=checkpointer)
