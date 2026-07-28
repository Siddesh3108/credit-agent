"""§11's Human Escalation and Handoff.

`build_handoff_package` constructs §11.2's HandoffPackage from structured
data, not a model's free-text summary -- `llm_summary` is the one field
that's LLM-generated, and it's clearly labeled as such and never the
source of truth for anything a human agent acts on (§11.2's own note).
"""
from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict

from app.domain.models import Decision


class HandoffPackage(TypedDict):
    ticket_id: str
    conversation_id: str
    identity_verification_level: str
    intent: Optional[str]
    entities: dict
    decision: Optional[Decision]
    attempted_actions: list
    priority: str
    suggested_next_step: str
    transcript_url: str
    audit_trail_url: str
    llm_summary: str


_PRIORITY_BY_REASON = {
    "backend_failure": "high",
    "unresolved_intent_ambiguity": "normal",
    "customer_requested_human": "normal",
    "repeated_identity_failure": "high",
    "fraud_signal": "urgent",
    "manual_review": "normal",
}

_NEXT_STEP_BY_REASON = {
    "backend_failure": "Retry or complete the pending action once the backend recovers; do not re-run without checking the audit trail for a partial success first.",
    "unresolved_intent_ambiguity": "Confirm what the customer actually needs; the bot could not disambiguate after one clarifying question.",
    "customer_requested_human": "Continue the conversation from where the customer left off -- no need to re-verify identity.",
    "repeated_identity_failure": "Route to identity verification per the specialized queue procedure; do not proceed with any account action until identity is confirmed.",
    "fraud_signal": "Route to fraud review immediately; do not disclose any watchlist/fraud-flag status to the customer.",
    "manual_review": "Review the policy decision's reason codes below and approve, deny, or request more information.",
}


def build_handoff_package(
    *,
    ticket_id: str,
    conversation_id: str,
    identity_verification_level: str,
    intent: Optional[str],
    entities: dict,
    decision: Optional[Decision],
    attempted_actions: list,
    escalation_reason: str,
    transcript_url: str,
    audit_trail_url: str,
    llm_summary: str = "",
) -> HandoffPackage:
    return HandoffPackage(
        ticket_id=ticket_id,
        conversation_id=conversation_id,
        identity_verification_level=identity_verification_level,
        intent=intent,
        entities=entities,
        decision=decision,
        attempted_actions=attempted_actions,
        priority=_PRIORITY_BY_REASON.get(escalation_reason, "normal"),
        suggested_next_step=_NEXT_STEP_BY_REASON.get(
            escalation_reason, "Review the conversation transcript and audit trail."
        ),
        transcript_url=transcript_url,
        audit_trail_url=audit_trail_url,
        llm_summary=llm_summary or "(no LLM summary generated)",
    )


def handoff_package_to_json(package: HandoffPackage) -> dict:
    """JSON-safe serialization for the ticketing adapter / API responses --
    `decision` is a dataclass (see domain/models.py's docstring on why),
    so it needs `.dict()` rather than falling out of a plain dict copy."""
    data = dict(package)
    if data.get("decision") is not None:
        data["decision"] = data["decision"].dict()
    return data
