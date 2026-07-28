"""§14's api/v1/audit.py: RBAC-protected read endpoints (§9.7 -- read
access is role-scoped to compliance/security/the case's assigned agent).

This reference implementation does not wire a real RBAC provider (no IdP
to check roles against, same caveat as app/core/security.py). The
endpoint shape and the "verify the chain on every read" behavior are real
and tested; the `Depends(require_audit_read_role)` placeholder is where a
real deployment plugs in its actual authorization check.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.v1.conversations import get_app_state
from app.bootstrap import AppState
from app.models.orm import AuditEventRow
from app.schemas.api import AuditEventOut, AuditTrailResponse

router = APIRouter(prefix="/audit", tags=["audit"])


def require_audit_read_role() -> None:
    """Placeholder for a real RBAC check (§9.7). Every request currently
    passes -- do not deploy this as-is; wire it to your real authz
    provider before granting audit read access to anyone."""
    return None


@router.get("/{session_id}", response_model=AuditTrailResponse, dependencies=[Depends(require_audit_read_role)])
def get_audit_trail(session_id: str, state: AppState = Depends(get_app_state)) -> AuditTrailResponse:
    verification = state.verifier.verify_session(session_id)

    with state.audit_writer._session_factory() as db:  # noqa: SLF001 -- read-only introspection
        stmt = (
            select(AuditEventRow)
            .where(AuditEventRow.session_id == session_id)
            .order_by(AuditEventRow.sequence_no.asc())
        )
        rows = db.execute(stmt).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="no audit events for this session")

    events = [
        AuditEventOut(
            event_id=r.event_id, sequence_no=r.sequence_no, occurred_at=r.occurred_at.isoformat(),
            actor=r.actor, event_type=r.event_type, decision=r.decision, reason_codes=r.reason_codes,
            event_hash=r.event_hash,
        )
        for r in rows
    ]
    return AuditTrailResponse(session_id=session_id, chain_intact=verification.intact, events=events)
