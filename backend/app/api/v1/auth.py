from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.conversations import get_app_state
from app.bootstrap import AppState
from app.schemas.api import AuthLoginRequest, AuthLoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthLoginResponse)
def login(request: Request, body: AuthLoginRequest, state: AppState = Depends(get_app_state)) -> AuthLoginResponse:
    secret = body.admin_secret
    if body.role == "admin":
        if secret != state.settings.admin_secret:
            raise HTTPException(status_code=403, detail="invalid admin secret")
        token = state.deps.auth_service.issue_session(body.customer_ref, role="admin")
        state.auth_tokens[token] = {
            "customer_ref": body.customer_ref,
            "conversation_id": None,
            "role": "admin",
        }
        return AuthLoginResponse(session_token=token, role="admin")

    if body.role != "customer":
        raise HTTPException(status_code=400, detail="unsupported role")

    token = state.deps.auth_service.issue_session(body.customer_ref, role="customer")
    return AuthLoginResponse(session_token=token, role="customer")
