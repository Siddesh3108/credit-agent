"""Enforces that `audit_events` cannot be UPDATEd or DELETEd (§9.4, §9.7).

Postgres path is §9.4's DDL verbatim (REVOKE + BEFORE trigger that raises).
SQLite has no row-level GRANT/REVOKE model, so the local-dev/test path uses
an equivalent BEFORE trigger only -- enough to make "audit_events is
append-only" a property this codebase actually tests, not just documents.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_POSTGRES_DDL = """
CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

_POSTGRES_TRIGGER = """
CREATE TRIGGER audit_events_no_update
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
"""


def install_audit_append_only_guard(engine: Engine, app_role: str | None = None) -> None:
    dialect = engine.dialect.name

    if dialect == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(_POSTGRES_DDL))
            conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events;"))
            conn.execute(text(_POSTGRES_TRIGGER))
            if app_role:
                # §9.4: the app's write role cannot UPDATE/DELETE at the
                # grant level either -- defense in depth alongside the
                # trigger, which also blocks superuser-owned connections
                # the GRANT system wouldn't stop.
                conn.execute(text(f'REVOKE UPDATE, DELETE ON audit_events FROM "{app_role}";'))
                conn.execute(text(f'GRANT INSERT, SELECT ON audit_events TO "{app_role}";'))

    elif dialect == "sqlite":
        with engine.begin() as conn:
            conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update;"))
            conn.execute(
                text(
                    """
                    CREATE TRIGGER audit_events_no_update
                    BEFORE UPDATE ON audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE is not permitted');
                    END;
                    """
                )
            )
            conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_delete;"))
            conn.execute(
                text(
                    """
                    CREATE TRIGGER audit_events_no_delete
                    BEFORE DELETE ON audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_events is append-only: DELETE is not permitted');
                    END;
                    """
                )
            )
    else:
        raise NotImplementedError(f"append-only guard not implemented for dialect={dialect!r}")
