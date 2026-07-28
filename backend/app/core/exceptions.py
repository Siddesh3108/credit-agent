"""Shared exception types with FastAPI-mappable status codes."""
from __future__ import annotations


class ServicingAgentError(Exception):
    status_code = 500


class AuthenticationRequiredError(ServicingAgentError):
    status_code = 401


class StepUpRequiredError(ServicingAgentError):
    status_code = 401


class SessionNotFoundError(ServicingAgentError):
    status_code = 404


class InvalidResumeStateError(ServicingAgentError):
    status_code = 409
