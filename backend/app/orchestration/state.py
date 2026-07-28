"""§5.1's state schema, verbatim."""
from __future__ import annotations

from typing import Literal, Optional

from typing_extensions import TypedDict


class ConversationState(TypedDict):
    session_id: str
    customer_ref: str  # opaque reference, never raw PII
    auth_level: Literal["unauthenticated", "authenticated", "step_up_verified"]
    messages: list
    intent: Optional[str]
    entities: dict
    task_queue: list
    clarification_attempts: int
    decision: Optional[dict]
    idempotency_key: Optional[str]
    escalation_reason: Optional[str]
