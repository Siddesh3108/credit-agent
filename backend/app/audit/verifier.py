"""Walks a session's event chain and recomputes hashes (§9.6).

This is the automated implementation of the "audit completeness" metric
in §1.3, designed to run continuously (e.g. on a schedule against every
recently-active session), not just before an audit.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.audit.models import GENESIS_HASH, compute_event_hash
from app.models.orm import AuditEventRow


@dataclass
class ChainVerificationResult:
    session_id: str
    intact: bool
    events_checked: int
    first_mismatch_sequence_no: int | None = None
    detail: str | None = None


class ChainVerifier:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def verify_session(self, session_id: str) -> ChainVerificationResult:
        with self._session_factory() as db:
            stmt = (
                select(AuditEventRow)
                .where(AuditEventRow.session_id == session_id)
                .order_by(AuditEventRow.sequence_no.asc())
            )
            rows = db.execute(stmt).scalars().all()

        if not rows:
            return ChainVerificationResult(session_id, True, 0, detail="no events for session")

        previous_hash = GENESIS_HASH
        for i, row in enumerate(rows):
            if row.sequence_no != i:
                return ChainVerificationResult(
                    session_id, False, len(rows), row.sequence_no,
                    detail=f"gap in sequence_no: expected {i}, found {row.sequence_no}",
                )
            if row.previous_hash != previous_hash:
                return ChainVerificationResult(
                    session_id, False, len(rows), row.sequence_no,
                    detail="previous_hash does not match prior event's event_hash",
                )
            recomputed = compute_event_hash(
                {
                    "event_id": row.event_id,
                    "occurred_at": row.occurred_at.isoformat(),
                    "sequence_no": row.sequence_no,
                    "session_id": row.session_id,
                    "actor": row.actor,
                    "event_type": row.event_type,
                    "decision": row.decision,
                    "reason_codes": row.reason_codes,
                },
                previous_hash,
            )
            if recomputed != row.event_hash:
                return ChainVerificationResult(
                    session_id, False, len(rows), row.sequence_no,
                    detail="event_hash does not match recomputed hash -- tampering or corruption",
                )
            previous_hash = row.event_hash

        return ChainVerificationResult(session_id, True, len(rows))

    def chain_intact(self, session_id: str) -> bool:
        return self.verify_session(session_id).intact

    def verify_all_sessions(self) -> list[ChainVerificationResult]:
        with self._session_factory() as db:
            session_ids = [
                row[0] for row in db.execute(select(AuditEventRow.session_id).distinct()).all()
            ]
        return [self.verify_session(sid) for sid in session_ids]
