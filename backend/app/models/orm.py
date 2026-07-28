"""SQLAlchemy ORM models for §13's data model plus §9.4's audit_events.

Cross-dialect design note: the design doc's DDL (§9.4) uses Postgres-native
UUID, TEXT[], and JSONB types. To let the exact same models run against
SQLite for fast local tests and against Postgres for anything resembling
production, the custom TypeDecorators below pick the native Postgres type
on that dialect and a portable equivalent (CHAR(36), JSON-encoded TEXT)
everywhere else. Nothing about the audit trail's actual guarantees (hash
chain, append-only) depends on which physical column type is used.
"""
from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import timezone
from typing import Any

from sqlalchemy import BigInteger, CHAR, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Always round-trips as a timezone-aware UTC datetime, on every dialect.

    Bug this fixes (found by tests/unit/test_audit_hash_chain.py): plain
    `DateTime(timezone=True)` round-trips correctly on Postgres (native
    TIMESTAMPTZ) but SQLite has no timezone-aware datetime type, so
    SQLAlchemy's SQLite dialect silently returns a naive datetime on read.
    `ChainVerifier` recomputes `occurred_at.isoformat()` as part of the
    hash -- a naive vs. aware datetime produces a different string
    ('...885498' vs '...885498+00:00') and therefore a different hash,
    which looked exactly like tampering despite nothing having been
    touched. This type forces both directions through UTC explicitly so
    the string used for hashing is reproducible regardless of backend.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class GUID(TypeDecorator):
    """Native UUID on Postgres, CHAR(36) string elsewhere."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return value
        return str(value)


class StringList(TypeDecorator):
    """TEXT[] on Postgres, JSON-encoded TEXT elsewhere."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_ARRAY(String))
        return dialect.type_descriptor(Text)

    def process_bind_param(self, value: Any, dialect) -> Any:
        value = value or []
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return []
        if dialect.name == "postgresql":
            return list(value)
        return json.loads(value)


class JSONBlob(TypeDecorator):
    """JSONB on Postgres, JSON-encoded TEXT elsewhere."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB)
        return dialect.type_descriptor(Text)

    def process_bind_param(self, value: Any, dialect) -> Any:
        value = value if value is not None else {}
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return {}
        if dialect.name == "postgresql":
            return dict(value)
        return json.loads(value)


def _uuid_str() -> str:
    return str(uuid_mod.uuid4())


class AuditEventRow(Base):
    """Maps 1:1 to §9.4's `audit_events` table / §9.2's AuditEvent schema."""

    __tablename__ = "audit_events"

    event_id = Column(GUID(), primary_key=True, default=_uuid_str)
    session_id = Column(GUID(), nullable=False, index=True)
    sequence_no = Column(BigInteger, nullable=False)
    occurred_at = Column(UTCDateTime(), nullable=False)
    actor = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    decision = Column(String, nullable=True)
    reason_codes = Column(StringList(), default=list, nullable=False)
    payload = Column(JSONBlob(), nullable=False, default=dict)
    previous_hash = Column(CHAR(64), nullable=False)
    event_hash = Column(CHAR(64), nullable=False)

    __table_args__ = (
        # §9.4 verbatim. This is what turns a race between two concurrent
        # appends to the same session into a hard DB-level failure (caught
        # and re-raised as AuditWriteError, §9.5's fail-closed path) rather
        # than two events silently claiming the same sequence_no.
        UniqueConstraint("session_id", "sequence_no", name="uq_audit_events_session_seq"),
    )


class ConversationRow(Base):
    """§13's `conversations` table."""

    __tablename__ = "conversations"

    conversation_id = Column(GUID(), primary_key=True, default=_uuid_str)
    customer_ref = Column(GUID(), nullable=False, index=True)
    channel = Column(String, nullable=False)
    started_at = Column(UTCDateTime(), nullable=False)
    ended_at = Column(UTCDateTime(), nullable=True)
    outcome = Column(String, nullable=True)
    langgraph_thread_id = Column(String, nullable=False, unique=True)


class MessageRow(Base):
    """§13's `messages` table."""

    __tablename__ = "messages"

    message_id = Column(GUID(), primary_key=True, default=_uuid_str)
    conversation_id = Column(GUID(), ForeignKey("conversations.conversation_id"), nullable=False)
    turn_index = Column(BigInteger, nullable=False)
    role = Column(String, nullable=False)  # customer | agent | system
    redacted_content = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    created_at = Column(UTCDateTime(), nullable=False)


class EscalationTicketRow(Base):
    """§13's `escalation_tickets` table."""

    __tablename__ = "escalation_tickets"

    ticket_id = Column(GUID(), primary_key=True, default=_uuid_str)
    conversation_id = Column(GUID(), ForeignKey("conversations.conversation_id"), nullable=False)
    trigger_reason = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    handoff_payload = Column(JSONBlob(), nullable=False)
    external_ticket_ref = Column(String, nullable=True)
    created_at = Column(UTCDateTime(), nullable=False)
    resolved_at = Column(UTCDateTime(), nullable=True)


class PolicyVersionRow(Base):
    """§13's `policy_versions` table (the Postgres-backed twin of the local
    JSON files in app/policy/config_versions/ -- see that module's README)."""

    __tablename__ = "policy_versions"

    version_id = Column(GUID(), primary_key=True, default=_uuid_str)
    intent = Column(String, nullable=False, index=True)
    effective_from = Column(UTCDateTime(), nullable=False)
    approved_by = Column(String, nullable=False)
    ruleset = Column(JSONBlob(), nullable=False)
    git_commit_sha = Column(String, nullable=False)
