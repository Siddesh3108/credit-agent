"""Env-driven settings (§14's app/config.py). All defaults here point at
the mock/local-dev stack so `uvicorn app.main:app` works with zero setup;
override via environment variables or a `.env` file for anything closer
to production (see .env.example at the repo root).
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        extra="ignore",
    )

    # Database. Postgres in anything resembling production (§9.4's
    # append-only guard has a real Postgres-specific path); sqlite here
    # only because it lets `uvicorn app.main:app` boot with zero external
    # services for a first look at the system.
    database_url: str = "sqlite:///./servicing_dev.db"
    app_write_role: str | None = None  # set for Postgres so REVOKE/GRANT (§9.4) actually applies

    # LLM (Stage 2 classifier, §4.1)
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"
    groq_api_key: str | None = None
    groq_model: str = "groq-text-1"

    # Policy config (§7.2, §13)
    policy_config_dir: str = str(APP_DIR / "policy" / "config_versions")
    intents_yaml_path: str = str(APP_DIR / "nlu" / "intents.yaml")

    # Fault injection for mock adapters (§8.5) -- leave at 0 unless you're
    # deliberately exercising resilience paths locally.
    fault_rate: float = 0.0
    latency_ms: int = 0

    # Local dev admin login secret. This is intentionally simple for a
    # reference/demo build; replace it before any non-local deployment.
    admin_secret: str = "admin123"

    # Dev-only endpoints (app/api/v1/dev.py) let you create/seed mock
    # accounts through the API instead of only the 3 hardcoded demo
    # accounts in scripts/seed_mock_data.py. They write directly into the
    # in-memory mock adapters with none of the real system's controls --
    # appropriate for a reference build talking to mock backends, actively
    # dangerous if this code is ever pointed at real adapters. Default
    # True here; set to False (or delete app/api/v1/dev.py) before this
    # is anything but a local demo.
    enable_dev_endpoints: bool = True

    cors_allow_origins: list = ["http://localhost:5173"]


def get_settings() -> Settings:
    return Settings()
