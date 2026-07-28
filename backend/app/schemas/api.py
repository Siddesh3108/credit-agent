from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class StartConversationRequest(BaseModel):
    customer_ref: str = Field(..., description="Opaque account/customer reference, never raw PII")
    channel: Literal["web", "mobile"] = "web"


class StartConversationResponse(BaseModel):
    conversation_id: str
    session_token: str


class AuthLoginRequest(BaseModel):
    customer_ref: str = Field(..., description="Opaque account/customer reference or admin identifier")
    role: Literal["customer", "admin"] = "customer"
    admin_secret: Optional[str] = None


class AuthLoginResponse(BaseModel):
    session_token: str
    role: Literal["customer", "admin"]
    conversation_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    message: str


class ResumeRequest(BaseModel):
    """Body for resuming a paused (interrupted) conversation.

    `kind="confirm"` resumes confirm_with_user (§15's confirmation click);
    `kind="human_decision"` resumes policy_check's manual_review pause
    (§5.4) from the human agent console.
    """
    kind: Literal["confirm", "human_decision"]
    confirmed: Optional[bool] = None
    outcome: Optional[Literal["approved", "denied"]] = None
    agent_id: Optional[str] = None
    note: Optional[str] = None


class ConversationTurnResponse(BaseModel):
    conversation_id: str
    status: Literal["awaiting_confirmation", "awaiting_human_review", "resolved", "escalated", "open"]
    intent: Optional[str] = None
    decision: Optional[dict] = None
    interrupt_payload: Optional[dict] = None
    escalation_reason: Optional[str] = None
    message: Optional[str] = None


class AuditEventOut(BaseModel):
    event_id: str
    sequence_no: int
    occurred_at: str
    actor: str
    event_type: str
    decision: Optional[str] = None
    reason_codes: list = []
    event_hash: str


class AuditTrailResponse(BaseModel):
    session_id: str
    chain_intact: bool
    events: list


class TranscriptMessage(BaseModel):
    role: Literal["customer", "agent", "system"]
    content: str
    intent: Optional[str] = None
    created_at: str


class ConversationTranscriptResponse(BaseModel):
    conversation_id: str
    customer_ref: str
    channel: Literal["web", "mobile"]
    started_at: str
    ended_at: Optional[str] = None
    outcome: Optional[str] = None
    status: str
    messages: list[TranscriptMessage]


class AdminRequestSummary(BaseModel):
    conversation_id: str
    started_at: str
    ended_at: Optional[str] = None
    last_message_at: Optional[str] = None
    outcome: Optional[str] = None
    status: str
    intent: Optional[str] = None


class AdminRequestsResponse(BaseModel):
    account_ref: str
    requests: list[AdminRequestSummary]


class HealthResponse(BaseModel):
    status: Literal["ok"]
