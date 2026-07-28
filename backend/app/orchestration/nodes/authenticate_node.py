"""Authenticate node (§5.2).

Reference-implementation scope note: initial OIDC session authentication
happens at the API Gateway/BFF layer (§3.1) before a conversation session
is created at all -- this node's job is narrower: gate on the auth_level
the API layer already established, and (via `require_step_up`, used by
policy_check_node) handle the *step-up* MFA challenges §10.4 requires
before specific sensitive actions. It does not implement §5.2's "failed
after 3 attempts" retry loop for *initial* login, since that belongs to
the OIDC provider integration, not this graph.
"""
from __future__ import annotations

from typing import Callable

from app.orchestration.state import ConversationState


def make_authenticate_node(audit_writer) -> Callable[[ConversationState], dict]:
    def authenticate_node(state: ConversationState) -> dict:
        if state.get("auth_level", "unauthenticated") == "unauthenticated":
            audit_writer.append(
                session_id=state["session_id"], actor="system", event_type="auth_event",
                payload={"result": "rejected", "reason": "no_valid_session"},
            )
            return {"escalation_reason": "authentication_required"}

        audit_writer.append(
            session_id=state["session_id"], actor="system", event_type="auth_event",
            payload={"result": "ok", "auth_level": state["auth_level"]},
        )
        return {}

    return authenticate_node
