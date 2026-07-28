"""§16.2's metric formulas -- implementation of §1.3's success metrics.

This module computes metrics from a list of already-run conversation
records; it does not itself run conversations. Wire it up to real
production data (or golden_conversations/ replays) by producing objects
with the attributes referenced below.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConversationRecord:
    outcome: str  # "resolved" | "escalated" | "abandoned"
    intent: str | None = None


@dataclass
class ActionRecord:
    session_id: str


def first_contact_resolution_rate(conversations: list[ConversationRecord]) -> float:
    if not conversations:
        return 0.0
    resolved = sum(1 for c in conversations if c.outcome == "resolved")
    return resolved / len(conversations)


def first_contact_resolution_rate_by_intent(
    conversations: list[ConversationRecord],
) -> dict[str, float]:
    """§4.4: "Classification accuracy is tracked per-intent... so a
    regression in one intent can't hide behind improvement in another."
    Same principle applied to FCR."""
    by_intent: dict[str, list[ConversationRecord]] = {}
    for c in conversations:
        by_intent.setdefault(c.intent or "unknown", []).append(c)
    return {intent: first_contact_resolution_rate(convs) for intent, convs in by_intent.items()}


def audit_completeness(actions: list[ActionRecord], verifier) -> float:
    """`verifier` is a ChainVerifier (app/audit/verifier.py)."""
    if not actions:
        return 1.0
    intact = sum(1 for a in actions if verifier.chain_intact(a.session_id))
    return intact / len(actions)
