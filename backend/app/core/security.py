"""§10.4's AuthN/AuthZ, reference-implementation version.

Production requires a real OIDC provider (Auth0/Okta/Cognito/etc.) plus a
real step-up MFA channel (SMS/TOTP/push) -- neither exists to integrate
with here. `LocalDevAuthService` below satisfies the same `AuthService`
Protocol with an in-memory session store and a fixed dev MFA code, so the
rest of the system (orchestrator, API layer) can be built and tested
against a real interface today and re-pointed at a real IdP later without
touching any calling code.

DEV ONLY: the fixed MFA code and in-memory session store below must never
ship to production. Nothing about the interface forces this; the warning
is the only thing standing between "convenient local dev" and "a real
security hole."
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Literal, Protocol

AuthLevel = Literal["unauthenticated", "authenticated", "step_up_verified"]
AuthRole = Literal["customer", "agent", "admin"]

DEV_ONLY_MFA_CODE = "000000"  # noqa: S105 -- intentionally obvious placeholder, never a real secret


@dataclass(frozen=True)
class AuthSession:
    customer_ref: str
    role: AuthRole
    auth_level: AuthLevel


class AuthService(Protocol):
    def issue_session(self, customer_ref: str, role: AuthRole = "customer") -> str: ...
    def get_session(self, token: str) -> AuthSession | None: ...
    def verify_session(self, token: str) -> AuthLevel: ...
    def step_up(self, token: str, mfa_code: str) -> bool: ...


@dataclass
class LocalDevAuthService:
    """DEV/TEST ONLY -- see module docstring."""

    _sessions: dict[str, AuthSession] = field(default_factory=dict)

    def issue_session(self, customer_ref: str, role: AuthRole = "customer") -> str:
        token = secrets.token_urlsafe(24)
        self._sessions[token] = AuthSession(
            customer_ref=customer_ref, role=role, auth_level="authenticated",
        )
        return token

    def get_session(self, token: str) -> AuthSession | None:
        return self._sessions.get(token)

    def verify_session(self, token: str) -> AuthLevel:
        session = self.get_session(token)
        if session is None:
            return "unauthenticated"
        return session.auth_level

    def step_up(self, token: str, mfa_code: str) -> bool:
        session = self.get_session(token)
        if session is None:
            return False
        if mfa_code != DEV_ONLY_MFA_CODE:
            return False
        self._sessions[token] = AuthSession(
            customer_ref=session.customer_ref,
            role=session.role,
            auth_level="step_up_verified",
        )
        return True
