from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.conversations import get_app_state
from app.bootstrap import AppState

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("")
def list_escalations(state: AppState = Depends(get_app_state)) -> dict:
    return {"tickets": state.deps.ticketing.tickets}

@router.get("/{ticket_ref}")
def get_escalation(ticket_ref: str, state: AppState = Depends(get_app_state)) -> dict:
    ticket = state.deps.ticketing.tickets.get(ticket_ref)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {"ticket_ref": ticket_ref, **ticket}


@router.post("/{ticket_ref}/resolve")
def resolve_escalation(
    ticket_ref: str, note: str = "", state: AppState = Depends(get_app_state)
) -> dict:
    ok = state.deps.ticketing.resolve_ticket(ticket_ref, note)
    if not ok:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {"ticket_ref": ticket_ref, "status": "resolved"}
