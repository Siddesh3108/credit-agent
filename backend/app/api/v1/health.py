from __future__ import annotations

from fastapi import APIRouter

from app.schemas.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    # A real readiness check would ping the DB / checkpointer connection
    # pool here rather than always returning ok.
    return HealthResponse(status="ok")
