"""Standalone audit-chain verification (§9.6): the automated
implementation of the §1.3 "audit completeness" metric. Run this on a
schedule against production; a non-zero exit code should page on-call as
a P1 regardless of time of day (§12.6).

Usage:
    python scripts/verify_audit_chain.py [--session-id SESSION_ID]
    python scripts/verify_audit_chain.py --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audit.verifier import ChainVerifier
from app.config import Settings
from app.db.session import build_engine, build_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", help="verify a single session")
    parser.add_argument("--all", action="store_true", help="verify every session with audit events")
    args = parser.parse_args()

    settings = Settings()
    engine = build_engine(settings.database_url)
    verifier = ChainVerifier(build_session_factory(engine))

    if args.session_id:
        results = [verifier.verify_session(args.session_id)]
    elif args.all:
        results = verifier.verify_all_sessions()
    else:
        parser.error("pass --session-id SESSION_ID or --all")
        return 2

    failures = [r for r in results if not r.intact]
    for r in results:
        status = "OK" if r.intact else "TAMPERED/CORRUPT"
        print(f"[{status}] session={r.session_id} events={r.events_checked} detail={r.detail or ''}")

    if failures:
        print(f"\n{len(failures)} session(s) FAILED verification. Page on-call (§12.6).", file=sys.stderr)
        return 1

    print(f"\nAll {len(results)} session(s) verified intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
