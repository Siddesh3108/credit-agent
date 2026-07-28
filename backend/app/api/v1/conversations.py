"""§14's api/v1/conversations.py: start, message, resume endpoints.

Translates between the HTTP layer and `graph.invoke()` / `Command(resume=...)`
-- everything about *how* a turn is decided still lives in
app/orchestration and app/policy; this module's job is session bookkeeping
and shaping responses, nothing more.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from langgraph.types import Command
from sqlalchemy import select, func

from app.bootstrap import AppState
from app.models.orm import ConversationRow, MessageRow
from app.schemas.api import (
    AdminRequestSummary,
    AdminRequestsResponse,
    ConversationTranscriptResponse,
    ConversationTurnResponse,
    ResumeRequest,
    SendMessageRequest,
    StartConversationRequest,
    StartConversationResponse,
    TranscriptMessage,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def _bearer_token(authorization: str | None) -> str | None:
    """Extracts the token from `Authorization: Bearer <token>` -- a query
    parameter was the first draft here and was wrong for a financial API:
    tokens in URLs get written to proxy/load-balancer access logs and
    cached in browser history, neither of which happens with a header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip()


def _graph_config(conversation_id: str) -> dict:
    return {"configurable": {"thread_id": conversation_id}}


def _shape_response(conversation_id: str, result: dict, interrupt_payload: dict | None = None) -> ConversationTurnResponse:
    if interrupt_payload:
        if interrupt_payload.get("type") == "confirm_action":
            status = "awaiting_confirmation"
        else:
            status = "awaiting_human_review"
        return ConversationTurnResponse(
            conversation_id=conversation_id, status=status, intent=result.get("intent"),
            decision=result.get("decision"), interrupt_payload=interrupt_payload,
        )

    if result.get("escalation_reason"):
        return ConversationTurnResponse(
            conversation_id=conversation_id, status="escalated", intent=result.get("intent"),
            decision=result.get("decision"), escalation_reason=result.get("escalation_reason"),
        )

    if (result.get("decision") or {}).get("outcome") == "clarify_info":
        return ConversationTurnResponse(
            conversation_id=conversation_id, status="open", intent=result.get("intent"),
            decision=result.get("decision"),
            message=(result.get("decision") or {})["clarification_message"],
        )

    return ConversationTurnResponse(
        conversation_id=conversation_id, status="resolved", intent=result.get("intent"),
        decision=result.get("decision"),
        message=None,
    )


def _require_conversation_access(session: dict | None, conversation_id: str) -> None:
    if session is None:
        raise HTTPException(status_code=401, detail="invalid or missing session token")
    if session["role"] == "customer" and session["conversation_id"] != conversation_id:
        raise HTTPException(status_code=403, detail="customer session required for this conversation")


def _conversation_status(ended_at: datetime | None, outcome: str | None) -> str:
    if outcome:
        return outcome
    return "resolved" if ended_at else "open"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("", response_model=StartConversationResponse)
def start_conversation(
    body: StartConversationRequest, state: AppState = Depends(get_app_state)
) -> StartConversationResponse:
    with state.session_factory() as db:
        existing = db.execute(
            select(ConversationRow)
            .where(ConversationRow.customer_ref == body.customer_ref)
            .where(ConversationRow.ended_at.is_(None))
            .order_by(ConversationRow.started_at.desc())
        ).scalars().first()
        
        if existing:
            conversation_id = str(existing.conversation_id)
        else:
            conversation_id = str(uuid.uuid4())
            db.add(ConversationRow(
                conversation_id=conversation_id,
                customer_ref=body.customer_ref,
                channel=body.channel,
                started_at=_now(),
                ended_at=None,
                outcome=None,
                langgraph_thread_id=conversation_id,
            ))
            db.commit()

    token = state.deps.auth_service.issue_session(body.customer_ref, role="customer")
    state.auth_tokens[token] = {
        "customer_ref": body.customer_ref,
        "conversation_id": conversation_id,
        "role": "customer",
    }
    return StartConversationResponse(conversation_id=conversation_id, session_token=token)


@router.post("/{conversation_id}/messages", response_model=ConversationTurnResponse)
def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_app_state),
) -> ConversationTurnResponse:
    session_token = _bearer_token(authorization)
    session = state.auth_tokens.get(session_token) if session_token else None
    if session is None or session.get("role") != "customer" or session.get("conversation_id") != conversation_id:
        raise HTTPException(status_code=401, detail="invalid or missing session token")

    auth_level = state.deps.auth_service.verify_session(session_token)
    config = _graph_config(conversation_id)

    with state.session_factory() as db:
        last_index = db.execute(
            select(func.max(MessageRow.turn_index)).where(MessageRow.conversation_id == conversation_id)
        ).scalar_one_or_none()
        turn_index = (last_index or -1) + 1
        db.add(MessageRow(
            conversation_id=conversation_id,
            turn_index=turn_index,
            role="customer",
            redacted_content=body.message,
            intent=None,
            created_at=_now(),
        ))
        db.commit()

    existing = state.graph.get_state(config)
    if existing.values:
        messages = [*existing.values.get("messages", []), {"role": "customer", "content": body.message}]
        graph_input = {"messages": messages, "auth_level": auth_level}
    else:
        graph_input = {
            "session_id": conversation_id, "customer_ref": session["customer_ref"],
            "auth_level": auth_level, "messages": [{"role": "customer", "content": body.message}],
            "intent": None, "entities": {}, "task_queue": [], "clarification_attempts": 0,
            "decision": None, "idempotency_key": None, "escalation_reason": None,
        }

    result = state.graph.invoke(graph_input, config)
    snapshot = state.graph.get_state(config)
    interrupt_payload = None
    if snapshot.tasks and snapshot.tasks[0].interrupts:
        interrupt_payload = snapshot.tasks[0].interrupts[0].value

    with state.session_factory() as db:
        last_index = db.execute(
            select(func.max(MessageRow.turn_index)).where(MessageRow.conversation_id == conversation_id)
        ).scalar_one_or_none()
        turn_index = (last_index or -1) + 1
        if interrupt_payload:
            status_calc = "awaiting_confirmation" if interrupt_payload.get("type") == "confirm_action" else "awaiting_human_review"
        elif result.get("escalation_reason"):
            status_calc = "escalated"
        elif (result.get("decision") or {}).get("outcome") == "clarify_info":
            status_calc = "open"
        else:
            status_calc = "resolved"

        if status_calc == "awaiting_confirmation":
            content = "Awaiting customer confirmation."
        elif status_calc == "awaiting_human_review":
            content = "Awaiting manual review by an admin."
        elif status_calc == "escalated":
            content = "Escalated to a specialist."
        elif (result.get("decision") or {}).get("outcome") == "clarify_info":
            content = (result.get("decision") or {})["clarification_message"]
        else:
            content = f"Resolved: {result.get('decision') or result.get('intent') or 'completed'}."
            
        db.add(MessageRow(
            conversation_id=conversation_id,
            turn_index=turn_index,
            role="agent",
            redacted_content=content,
            intent=result.get("intent"),
            created_at=_now(),
        ))
        if status_calc in {"resolved", "escalated"}:
            conversation = db.get(ConversationRow, conversation_id)
            if conversation:
                conversation.ended_at = _now()
                conversation.outcome = result.get("decision", {}).get("outcome") if isinstance(result.get("decision"), dict) else status_calc
        db.commit()

    return _shape_response(conversation_id, result, interrupt_payload=interrupt_payload)


@router.post("/{conversation_id}/resume", response_model=ConversationTurnResponse)
def resume_conversation(
    conversation_id: str,
    body: ResumeRequest,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_app_state),
) -> ConversationTurnResponse:
    """`Authorization` is required to resume a confirm_with_user pause
    (the customer confirming/cancelling); a human_decision resume comes
    from the internal agent console and is authorized only for admin
    sessions in this reference build.
    """
    config = _graph_config(conversation_id)
    existing = state.graph.get_state(config)
    if not existing.next:
        raise HTTPException(status_code=409, detail="conversation is not currently paused")

    session_token = _bearer_token(authorization)
    if session_token is None or session_token not in state.auth_tokens:
        raise HTTPException(status_code=401, detail="invalid or missing session token")

    session = state.auth_tokens[session_token]
    if body.kind == "confirm":
        if session["role"] != "customer" or session["conversation_id"] != conversation_id:
            raise HTTPException(status_code=403, detail="customer session required for confirmation")
        resume_value = {"confirmed": bool(body.confirmed)}
        log_role = "customer"
        log_content = f"Customer confirmed: {bool(body.confirmed)}"
    else:
        if session["role"] != "admin":
            raise HTTPException(status_code=403, detail="admin session required for manual review decisions")
        resume_value = {"outcome": body.outcome, "agent_id": body.agent_id, "note": body.note or ""}
        log_role = "agent"
        log_content = f"Admin decision: {body.outcome} ({body.agent_id})"

    result = state.graph.invoke(Command(resume=resume_value), config)
    snapshot = state.graph.get_state(config)
    interrupt_payload = None
    if snapshot.tasks and snapshot.tasks[0].interrupts:
        interrupt_payload = snapshot.tasks[0].interrupts[0].value

    with state.session_factory() as db:
        last_index = db.execute(
            select(func.max(MessageRow.turn_index)).where(MessageRow.conversation_id == conversation_id)
        ).scalar_one_or_none()
        turn_index = (last_index or -1) + 1
        
        if interrupt_payload:
            status_calc = "awaiting_confirmation" if interrupt_payload.get("type") == "confirm_action" else "awaiting_human_review"
        elif result.get("escalation_reason"):
            status_calc = "escalated"
        elif (result.get("decision") or {}).get("outcome") == "clarify_info":
            status_calc = "open"
        else:
            status_calc = "resolved"
            
        db.add(MessageRow(
            conversation_id=conversation_id,
            turn_index=turn_index,
            role=log_role,
            redacted_content=log_content,
            intent=result.get("intent"),
            created_at=_now(),
        ))
        if status_calc in {"resolved", "escalated"}:
            conversation = db.get(ConversationRow, conversation_id)
            if conversation:
                conversation.ended_at = _now()
                conversation.outcome = result.get("decision", {}).get("outcome") if isinstance(result.get("decision"), dict) else status_calc
        db.commit()

    return _shape_response(conversation_id, result, interrupt_payload=interrupt_payload)


@router.get("/{conversation_id}", response_model=ConversationTurnResponse)
def get_conversation(
    conversation_id: str, state: AppState = Depends(get_app_state)
) -> ConversationTurnResponse:
    config = _graph_config(conversation_id)
    existing = state.graph.get_state(config)
    if not existing.values:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _shape_response(conversation_id, dict(existing.values))


@router.get("/{conversation_id}/transcript", response_model=ConversationTranscriptResponse)
def get_conversation_transcript(
    conversation_id: str,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_app_state),
) -> ConversationTranscriptResponse:
    session_token = _bearer_token(authorization)
    session = state.auth_tokens.get(session_token) if session_token else None
    _require_conversation_access(session, conversation_id)

    with state.session_factory() as db:
        conversation = db.get(ConversationRow, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="conversation not found")

        stmt = (
            select(MessageRow)
            .where(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.turn_index.asc())
        )
        rows = db.execute(stmt).scalars().all()

    messages = [
        TranscriptMessage(
            role=r.role, content=r.redacted_content, intent=r.intent, created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]

    return ConversationTranscriptResponse(
        conversation_id=conversation.conversation_id,
        customer_ref=conversation.customer_ref,
        channel=conversation.channel,
        started_at=conversation.started_at.isoformat(),
        ended_at=conversation.ended_at.isoformat() if conversation.ended_at else None,
        outcome=conversation.outcome,
        status=_conversation_status(conversation.ended_at, conversation.outcome),
        messages=messages,
    )


@router.get("/account/{account_ref}/requests", response_model=AdminRequestsResponse)
def list_account_requests(
    account_ref: str,
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_app_state),
) -> AdminRequestsResponse:
    session_token = _bearer_token(authorization)
    session = state.auth_tokens.get(session_token) if session_token else None
    if session is None:
        raise HTTPException(status_code=401, detail="invalid or missing session token")
    if session["role"] != "admin" and session["customer_ref"] != account_ref:
        raise HTTPException(status_code=403, detail="admin or customer session required")

    with state.session_factory() as db:
        stmt = (
            select(ConversationRow)
            .where(ConversationRow.customer_ref == account_ref)
            .order_by(ConversationRow.started_at.desc())
        )
        rows = db.execute(stmt).scalars().all()

        requests = []
        for r in rows:
            last_message_at = db.execute(
                select(func.max(MessageRow.created_at)).where(MessageRow.conversation_id == r.conversation_id)
            ).scalar_one_or_none()
            requests.append(
                AdminRequestSummary(
                    conversation_id=r.conversation_id,
                    started_at=r.started_at.isoformat(),
                    ended_at=r.ended_at.isoformat() if r.ended_at else None,
                    last_message_at=last_message_at.isoformat() if last_message_at else None,
                    outcome=r.outcome,
                    status=_conversation_status(r.ended_at, r.outcome),
                    intent=None,
                )
            )

    return AdminRequestsResponse(account_ref=account_ref, requests=requests)
