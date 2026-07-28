"""Engine + session-factory construction, shared by the app and tests.

Deliberately thin: callers own the engine's lifecycle (creation, disposal)
so tests can point this at an ephemeral SQLite file or a real Postgres
instance without any code here caring which.
"""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.append_only_guard import install_audit_append_only_guard
from app.models.orm import Base


def build_engine(database_url: str, **kwargs):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, **kwargs)


def init_schema(engine, app_role: str | None = None) -> None:
    """Creates all tables and installs the audit append-only guard.

    In a real deployment this is what Alembic's migration does (see
    backend/alembic/versions/0001_initial.py) -- this function exists so
    tests and the `seed_mock_data.py` script can stand up an equivalent
    schema without running Alembic.
    """
    Base.metadata.create_all(engine)
    install_audit_append_only_guard(engine, app_role=app_role)


def build_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
