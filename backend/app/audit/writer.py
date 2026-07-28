"""Hash-chained, append-only audit writer (§9.2-9.5).

Implements the transactional-outbox pattern from §9.5: the event is
durably committed before the caller may treat the thing it describes as
"about to happen." AuditWriteError is the single exception type callers
need to catch to implement Principle 2's fail-closed rule (§2): if this
raises, the action it was about to log must not proceed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit.models import GENESIS_HASH, AuditEvent, compute_event_hash
from app.models.orm import AuditEventRow


class AuditWriteError(RuntimeError):
    """Raised whenever a durable audit write cannot be completed -- wraps
    the underlying DB exception so callers have exactly one type to catch
    for the fail-closed boundary (§2 Principle 2, §9.5, §12.2's "Audit
    write path" row)."""


class AuditTrailWriter:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def _last_event(self, db: Session, session_id: str) -> AuditEventRow | None:
        stmt = (
            select(AuditEventRow)
            .where(AuditEventRow.session_id == session_id)
            .order_by(AuditEventRow.sequence_no.desc())
            .limit(1)
        )
        return db.execute(stmt).scalars().first()

    def append(
        self,
        *,
        session_id: str,
        actor: str,
        event_type: str,
        decision: str | None = None,
        reason_codes: list | None = None,
        payload: dict | None = None,
    ) -> AuditEvent:
        reason_codes = reason_codes or []
        payload = payload or {}

        try:
            with self._session_factory() as db:
                last = self._last_event(db, session_id)
                previous_hash = last.event_hash if last else GENESIS_HASH
                sequence_no = (last.sequence_no + 1) if last else 0

                event: AuditEvent = {
                    "event_id": str(uuid4()),
                    "session_id": session_id,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "sequence_no": sequence_no,
                    "actor": actor,
                    "event_type": event_type,
                    "decision": decision,
                    "reason_codes": reason_codes,
                    "payload": payload,
                    "previous_hash": previous_hash,
                    "event_hash": "",
                }
                event["event_hash"] = compute_event_hash(event, previous_hash)

                row = AuditEventRow(
                    event_id=event["event_id"],
                    session_id=event["session_id"],
                    sequence_no=event["sequence_no"],
                    occurred_at=datetime.fromisoformat(event["occurred_at"]),
                    actor=event["actor"],
                    event_type=event["event_type"],
                    decision=event["decision"],
                    reason_codes=event["reason_codes"],
                    payload=event["payload"],
                    previous_hash=event["previous_hash"],
                    event_hash=event["event_hash"],
                )
                db.add(row)
                db.commit()
                return event
        except AuditWriteError:
            raise
        except Exception as exc:  # noqa: BLE001 - intentional fail-closed boundary
            raise AuditWriteError(
                f"audit write failed for session_id={session_id!r} event_type={event_type!r}"
            ) from exc
