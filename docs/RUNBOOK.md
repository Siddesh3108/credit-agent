# Runbook

Every command below was actually run against this repo during
development, not just written and assumed correct.

## Local development (no Docker, no Postgres)

```bash
cd backend
pip install -e ".[dev]" --break-system-packages
pytest -q                              # 97 passed, 9 skipped (the skips are Postgres-only tests)
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for interactive API docs (FastAPI's
auto-generated Swagger UI — confirmed working via a real running server,
not just TestClient).

In a second terminal:

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173, proxies /v1/* to localhost:8000
```

The mock backends are empty until seeded — see README.md's Quickstart for
a one-liner, or adapt `scripts/seed_mock_data.py`.

## Running against real Postgres

```bash
# Start Postgres (adjust for your platform -- this assumes it's already
# installed; apt-get install postgresql on Debian/Ubuntu)
service postgresql start   # or: pg_ctlcluster / systemctl start postgresql

# Provision the app role and database (§9.4's REVOKE/GRANT model needs
# this role to exist)
sudo -u postgres psql -c "CREATE ROLE app_write_role LOGIN PASSWORD 'localdev';"
sudo -u postgres psql -c "CREATE DATABASE servicing;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE servicing TO app_write_role;"
sudo -u postgres psql -d servicing -c "GRANT ALL ON SCHEMA public TO app_write_role;"

export DATABASE_URL="postgresql+psycopg://app_write_role:localdev@localhost:5432/servicing"
export APP_WRITE_ROLE="app_write_role"

cd backend
pytest -q   # now 97 passed, 0 skipped -- the Postgres-parametrized audit tests actually run
uvicorn app.main:app --reload
```

`app.db.session.init_schema()` creates all tables and installs the
append-only trigger + REVOKE on startup — no separate migration step
needed for local dev. For a real deployment, use the Alembic migration in
`backend/alembic/` instead of relying on `init_schema`'s auto-create, so
schema changes go through review.

## Verifying the audit chain

```bash
cd backend
python3 scripts/verify_audit_chain.py --all
```

Exit code 0 means every session's hash chain recomputes correctly from
genesis. Non-zero means something is wrong — page on-call immediately
(§12.6), don't retry-and-see.

## Swapping in the real Stage 2 LLM classifier

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

That's it — `app/bootstrap.py` picks it up automatically and switches
from `FakeLLMClassifier` to `AnthropicLLMClassifier`. Verify the model
name in `app/config.py` (`LLM_MODEL`, defaults to `claude-sonnet-5`)
against https://docs.claude.com before deploying — model names and
pricing change.

## Swapping in a durable (Postgres) LangGraph checkpointer

`app/bootstrap.py` currently uses `InMemorySaver` so the app boots with
zero setup. For anything that needs a conversation to survive a restart
(§5.3), swap it for `PostgresSaver`:

```python
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
    checkpointer.setup()  # run once, in a migration step -- never in the request path (§5.5)
    graph = build_graph(deps, audit_writer, checkpointer)
```

This is §5.3's code sample verbatim (with `settings.database_url` in
place of the doc's hardcoded connection string) — it was validated
against the real `langgraph-checkpoint-postgres` package during
development (confirmed `PostgresSaver` is importable and has a
`.from_conn_string()` classmethod as expected), but the full
`app.invoke()`-through-`PostgresSaver` path specifically was not
re-exercised after wiring it into `bootstrap.py` — the interrupt/resume
mechanics were validated against `InMemorySaver` in the test suite. Treat
this swap as "should work, confirm it before depending on it," not
"proven."

## Known warnings

- `StarletteDeprecationWarning: Using httpx with starlette.testclient is
  deprecated; install httpx2 instead` — cosmetic, from the test suite's
  use of FastAPI's TestClient, doesn't affect the application itself.
