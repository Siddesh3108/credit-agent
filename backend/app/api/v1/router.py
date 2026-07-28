from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import audit, conversations, dev, escalations, health

api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router)
api_router.include_router(conversations.router)
api_router.include_router(escalations.router)
api_router.include_router(audit.router)
api_router.include_router(dev.router)
from app.api.v1.auth import router as auth_router
api_router.include_router(auth_router)
