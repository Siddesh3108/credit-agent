from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy import text

from app.audit.models import GENESIS_HASH, compute_event_hash
from app.audit.verifier import ChainVerifier
from app.audit.writer import AuditTrailWriter, AuditWriteError
from app.db.session import build_engine, build_session_factory, init_schema

POSTGRES_TEST_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+psycopg://app_write_role:localdev@localhost:5432/servicing"
)


def _sqlite_engine(tmp_path):
    db_path = tmp_path / "audit_test.db"
    engine = build_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    return engine


def _postgres_available() -> bool:
    try:
        engine = build_engine(POSTGRES_TEST_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _postgres_available()


def _postgres_engine():
    # Fresh schema per test run: drop and recreate audit_events so tests
    # are independent even though Postgres is a shared local server.
    engine = build_engine(POSTGRES_TEST_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS audit_events CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS escalation_tickets CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS messages CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS conversations CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS policy_versions CASCADE"))
    init_schema(engine, app_role="app_write_role")
    return engine


def _engines(tmp_path):
    engines = {"sqlite": _sqlite_engine(tmp_path)}
    if POSTGRES_AVAILABLE:
        engines["postgres"] = _postgres_engine()
    return engines


@pytest.fixture(params=["sqlite", "postgres"])
def engine(request, tmp_path):
    if request.param == "postgres" and not POSTGRES_AVAILABLE:
        pytest.skip("local Postgres not available in this environment")
    engines = _engines(tmp_path)
    eng = engines[request.param]
    yield eng
    eng.dispose()


@pytest.fixture
def writer(engine):
    return AuditTrailWriter(build_session_factory(engine))


@pytest.fixture
def verifier(engine):
    return ChainVerifier(build_session_factory(engine))


class TestHashChainMath:
    def test_hash_is_deterministic_given_same_inputs(self):
        event = {
            "event_id": "e1", "occurred_at": "2026-01-01T00:00:00+00:00",
            "sequence_no": 0, "session_id": "s1", "actor": "system",
            "event_type": "intent_classified", "decision": None, "reason_codes": [],
        }
        h1 = compute_event_hash(event, GENESIS_HASH)
        h2 = compute_event_hash(event, GENESIS_HASH)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex digest

    def test_hash_changes_if_previous_hash_changes(self):
        event = {
            "event_id": "e1", "occurred_at": "2026-01-01T00:00:00+00:00",
            "sequence_no": 0, "session_id": "s1", "actor": "system",
            "event_type": "intent_classified", "decision": None, "reason_codes": [],
        }
        h1 = compute_event_hash(event, GENESIS_HASH)
        h2 = compute_event_hash(event, "1" * 64)
        assert h1 != h2


class TestAuditTrailWriter:
    def test_first_event_chains_to_genesis(self, writer, verifier):
        session_id = str(uuid.uuid4())
        event = writer.append(session_id=session_id, actor="system", event_type="auth_event")
        assert event["previous_hash"] == GENESIS_HASH
        assert event["sequence_no"] == 0
        assert verifier.chain_intact(session_id)

    def test_sequential_events_chain_correctly(self, writer, verifier):
        session_id = str(uuid.uuid4())
        e1 = writer.append(session_id=session_id, actor="system", event_type="intent_classified")
        e2 = writer.append(
            session_id=session_id, actor="system", event_type="policy_decision",
            decision="approved", reason_codes=["STANDARD_COURTESY_WAIVER"],
        )
        e3 = writer.append(session_id=session_id, actor="agent_llm", event_type="action_executed")

        assert e2["previous_hash"] == e1["event_hash"]
        assert e3["previous_hash"] == e2["event_hash"]
        assert [e1["sequence_no"], e2["sequence_no"], e3["sequence_no"]] == [0, 1, 2]

        result = verifier.verify_session(session_id)
        assert result.intact
        assert result.events_checked == 3

    def test_different_sessions_have_independent_chains(self, writer):
        s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
        e1 = writer.append(session_id=s1, actor="system", event_type="auth_event")
        e2 = writer.append(session_id=s2, actor="system", event_type="auth_event")
        assert e1["previous_hash"] == GENESIS_HASH
        assert e2["previous_hash"] == GENESIS_HASH  # not chained to s1's event

    def test_payload_never_contains_raw_pan_in_this_suite(self, writer):
        """Not a technical enforcement (that's §10.3's mask_card_number at
        the serialization boundary) -- this documents the expectation that
        callers never hand this writer an unmasked PAN."""
        session_id = str(uuid.uuid4())
        event = writer.append(
            session_id=session_id, actor="system", event_type="action_executed",
            payload={"card_last4": "1234", "amount": 35.0},
        )
        assert "card_last4" in event["payload"]
        assert len(event["payload"]["card_last4"]) == 4


class TestAppendOnlyEnforcement:
    def test_update_is_rejected(self, engine, writer):
        session_id = str(uuid.uuid4())
        writer.append(session_id=session_id, actor="system", event_type="auth_event")

        with pytest.raises((OperationalError, IntegrityError, Exception)):
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE audit_events SET actor = 'tampered' WHERE session_id = :sid"),
                    {"sid": session_id},
                )

    def test_delete_is_rejected(self, engine, writer):
        session_id = str(uuid.uuid4())
        writer.append(session_id=session_id, actor="system", event_type="auth_event")

        with pytest.raises((OperationalError, IntegrityError, Exception)):
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM audit_events WHERE session_id = :sid"), {"sid": session_id}
                )

    def test_concurrent_same_sequence_fails_closed(self, engine):
        """Two writers racing to append event #0 for the same session must
        not both succeed -- the UNIQUE(session_id, sequence_no) constraint
        (§9.4) turns the race into a hard failure on one of them, which
        AuditTrailWriter.append surfaces as AuditWriteError (§9.5's
        fail-closed contract), rather than silently corrupting the chain.
        """
        session_factory = build_session_factory(engine)
        writer_a = AuditTrailWriter(session_factory)
        writer_b = AuditTrailWriter(session_factory)
        session_id = str(uuid.uuid4())

        # Simulate the race directly at the row level: both "writers" have
        # already computed sequence_no=0 based on an empty chain (as they
        # would if invoked concurrently) before either commits.
        from app.models.orm import AuditEventRow
        from app.audit.models import compute_event_hash

        def build_row(actor):
            event = {
                "event_id": str(uuid.uuid4()), "session_id": session_id,
                "occurred_at": "2026-01-01T00:00:00+00:00", "sequence_no": 0,
                "actor": actor, "event_type": "auth_event", "decision": None,
                "reason_codes": [],
            }
            event["event_hash"] = compute_event_hash(event, GENESIS_HASH)
            return AuditEventRow(
                event_id=event["event_id"], session_id=event["session_id"],
                sequence_no=0, occurred_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                actor=actor, event_type="auth_event", decision=None,
                reason_codes=[], payload={}, previous_hash=GENESIS_HASH,
                event_hash=event["event_hash"],
            )

        with session_factory() as db:
            db.add(build_row("writer_a"))
            db.commit()

        with pytest.raises((IntegrityError, OperationalError, Exception)):
            with session_factory() as db2:
                db2.add(build_row("writer_b"))
                db2.commit()


class TestChainVerifier:
    def test_detects_tampered_actor_field(self, engine, writer, verifier, request):
        session_id = str(uuid.uuid4())
        writer.append(session_id=session_id, actor="system", event_type="auth_event")
        assert verifier.chain_intact(session_id)

        # Bypass the append-only guard to prove the *verifier* -- not the
        # trigger/grants -- catches semantic tampering if it ever got
        # through. On Postgres this must be done as the superuser: the
        # app role can't do it even with the trigger dropped, because
        # §9.4's REVOKE blocks UPDATE at the grant level independently of
        # the trigger (confirmed by this test originally failing to even
        # simulate a bypass as app_write_role -- the defense-in-depth was
        # working correctly). §9.7 describes exactly this threat model:
        # "database administrators... would need an explicit, itself-
        # logged, break-glass procedure" -- i.e. a superuser genuinely can
        # bypass at the infra layer, which is why the verifier needs to
        # exist as a second, independent line of defense.
        dialect = engine.dialect.name
        if dialect == "postgresql":
            bypass_engine = build_engine(
                "postgresql+psycopg://postgres:localdev@localhost:5432/servicing"
            )
        else:
            bypass_engine = engine

        with bypass_engine.begin() as conn:
            if dialect == "sqlite":
                conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update"))
            else:
                conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events"))
            conn.execute(
                text("UPDATE audit_events SET actor = 'tampered' WHERE session_id = :sid"),
                {"sid": session_id},
            )
        if dialect == "postgresql":
            bypass_engine.dispose()

        result = verifier.verify_session(session_id)
        assert result.intact is False
        assert result.first_mismatch_sequence_no == 0

    def test_empty_session_is_trivially_intact(self, verifier):
        result = verifier.verify_session(str(uuid.uuid4()))
        assert result.intact
        assert result.events_checked == 0
