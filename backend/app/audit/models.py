"""§9.2's AuditEvent schema and §9.3's hash-chain math.

Kept as a standalone module (no SQLAlchemy import) so the hash computation
itself -- the part a security review will want to independently
recompute -- has zero framework dependencies and can be lifted into a
standalone verification script.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from typing_extensions import TypedDict

GENESIS_HASH = "0" * 64


class AuditEvent(TypedDict):
    event_id: str
    session_id: str
    occurred_at: str
    sequence_no: int
    actor: str
    event_type: str
    decision: Optional[str]
    reason_codes: list
    payload: dict
    previous_hash: str
    event_hash: str


def compute_event_hash(event: dict, previous_hash: str) -> str:
    """§9.3 verbatim: canonical JSON of the event's identity fields, chained
    to the previous event's hash, SHA-256'd.

    Notice `payload` is NOT one of the hashed fields -- this matches the
    doc's own §9.3 code sample exactly, and it is not an oversight: §9.8
    describes crypto-shredding PII inside `payload` on an erasure request
    (destroy the per-customer key, not the event row). That only works
    because `payload` sits outside the hash chain -- if it were hashed,
    shredding it would break every subsequent event's hash. The chain
    anchors the fields that must never change (sequence, actor, decision,
    reason_codes), while `payload` can be selectively redacted later
    without invalidating chain integrity. Worth knowing as a reviewer: this
    means the hash chain does NOT, by itself, detect tampering with
    payload contents -- only with the decision/sequence/actor fields. If a
    field inside payload ever needs the same tamper-evidence guarantee,
    promote it out of payload and into the hashed fields above.
    """
    canonical_input = {
        "event_id": event["event_id"],
        "occurred_at": event["occurred_at"],
        "sequence_no": event["sequence_no"],
        "session_id": event["session_id"],
        "actor": event["actor"],
        "event_type": event["event_type"],
        "decision": event.get("decision"),
        "reason_codes": event.get("reason_codes", []),
        "previous_hash": previous_hash,
    }
    canonical = json.dumps(canonical_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
