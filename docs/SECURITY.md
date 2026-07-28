# Security notes

This is an engineering summary of what's implemented, not a security
audit and not a substitute for one. See design doc §10 for the full
threat model this implementation follows.

## What's implemented and tested

- **PII redaction before any LLM call** (`app/core/pii_redaction.py`):
  SSN pattern + Luhn-validated card number detection, tested against a
  well-known public test card number and against false positives on
  random 16-digit sequences that fail the Luhn check.
- **Card number masking** (`mask_card_number`): last-4-only display,
  tested.
- **Append-only audit trail** (§9.4): REVOKE + trigger on Postgres,
  trigger-only on SQLite, both tested by attempting UPDATE/DELETE and
  asserting failure — including a test that specifically confirms the
  *grant-level* REVOKE blocks the app role even after the trigger is
  dropped (defense in depth actually verified, not assumed).
- **Idempotency keys** on every mock adapter write (§8.2), tested by
  replaying the same key and asserting an identical result rather than a
  duplicate effect.
- **Fail-closed audit writes** (§9.5): `AuditWriteError` is the only
  exception type callers see; nothing in this codebase has a path that
  reaches a backend write after a failed audit write.

## What's explicitly NOT implemented (stubs, not gaps hidden as done)

- **OIDC / real MFA** — `app/core/security.py`'s `LocalDevAuthService`
  has a hardcoded dev-only MFA code and an in-memory session store. Its
  own module docstring says not to deploy it. There is no code path here
  that makes this production-safe; it needs a real IdP integration.
- **OFAC / sanctions screening** — `mock_fraud_service.py` ships with
  zero real sanctioned-entity data on purpose. A hardcoded "OFAC list" in
  a reference repo would go stale immediately and could create a false
  sense of compliance coverage. This must be backed by a real screening
  vendor before production.
- **KMS / field-level encryption** (§10.2) — not implemented. No
  Tier 0/1 raw values (PAN, SSN, full account number) are stored in this
  application's own database at all (see design doc §13's note and this
  repo's data model, which only ever stores references), which reduces
  but doesn't eliminate the need for encryption-at-rest on whatever *is*
  stored.
- **RBAC on the audit-read endpoint** — `app/api/v1/audit.py`'s
  `require_audit_read_role` dependency is a no-op placeholder. Every
  request currently passes. Wire it to a real authz check before this
  endpoint is reachable by anyone outside a trusted network.

## If you're reviewing this for a real deployment

Start with the "What's explicitly NOT implemented" list above — that's
the actual gap list. The "What's implemented and tested" list tells you
what's been checked, not what's safe to trust blindly; re-verify
independently regardless.
