# Card Servicing Agent — Reference Implementation

A working, tested implementation of the [End-to-End Card Servicing Agent
design doc](./card_servicing_agent_design.pdf) (v1.0, July 25 2026): a
conversational agent that resolves fee reversals, credit limit increases,
and card replacements, with a deterministic policy engine as the sole
approval authority and a cryptographically verifiable audit trail.

**97 backend tests pass** (`cd backend && pytest -q`), including the full
suite parametrized against a real local Postgres, and the frontend
builds clean (`cd frontend && npm run build`). This document tells you
exactly what that coverage means and doesn't mean — read
["What's real vs. scaffolded"](#whats-real-vs-scaffolded) before you trust
any of it with real money.

## Quickstart

```bash
# 1. Backend
cd backend
pip install -e ".[dev]" --break-system-packages   # or use a venv
pytest -q                                          # 97 passed (Postgres tests skip without one running)
uvicorn app.main:app --reload                      # http://localhost:8000/docs for interactive API docs

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev                                         # http://localhost:5173
```

No API key, no Postgres, no Docker required to see it run — the backend
defaults to SQLite and fully-mocked backends (§8.5 of the design doc).
Type "please waive my late fee" and it'll tell you it can't find your
account, because nothing's seeded yet. Seed some demo data first:

```bash
cd backend
python3 -c "
from app.bootstrap import build_app_state
from app.config import Settings
from scripts.seed_mock_data import seed
import app.main as m
state = build_app_state(Settings())
seed(state)
m.app.state.app_state = state
import uvicorn
uvicorn.run(m.app, host='127.0.0.1', port=8000)
"
```

Then in the frontend, log in with `acct_001` and try: *"please waive my
late fee"*, *"my card was stolen"*, or *"can you raise my credit limit to
6000"*.

## Running fully "live" for free

**Get a free API key.** Sign up at [platform.claude.com](https://platform.claude.com)
(Settings → API keys → Create key). New accounts get a small free credit
to test with — no cost to try this. Set `LLM_MODEL=claude-haiku-4-5-20251001`
in your `.env` (see `.env.example`) rather than the pricier default —
Haiku is plenty for a classification task this size and stretches free
credit much further. A single Stage-2 classification call here is a few
hundred tokens; expect a free trial credit to cover several thousand
turns, not a handful. Verify current pricing/model names at
[docs.claude.com](https://docs.claude.com) before relying on any specific
number, including this one.

**Not limited to 3 hardcoded accounts.** `POST /v1/dev/accounts` (see
`app/api/v1/dev.py`) creates any account scenario on the fly:

```bash
curl -X POST http://localhost:8000/v1/dev/accounts -H "Content-Type: application/json" -d '{
  "account_ref": "my_test_acct",
  "current_limit": 5000,
  "fee": {"fee_type": "late_fee", "amount": 35}
}'
```
Then start a conversation with `"customer_ref": "my_test_acct"`. Push
`fee.amount` above the policy's auto-approval ceiling, or set
`days_past_due` > 0, to see the manual-review and delinquency paths.
This endpoint is dev-only by design (writes straight into the in-memory
mocks with zero authorization) — set `ENABLE_DEV_ENDPOINTS=false` before
this is anything but a local demo.

## What's real vs. scaffolded

This is the section to actually read. "Verified" means something specific
here: I mean I ran it and it passed, against the real target (Postgres,
real LangGraph, a real HTTP server), not that the code looks plausible.

| Component | Status | Verified how |
|---|---|---|
| Policy engine (§7) | **Real, fully tested** | 19 unit tests, one per branch/reason code |
| Audit trail (§9) | **Real, fully tested** | 20 tests incl. the exact §9.4 DDL against real local Postgres — REVOKE/trigger append-only enforcement, hash chain, fail-closed writes |
| Circuit breaker / retry / idempotency (§8.2-8.3) | **Real, fully tested** | 14 chaos tests with a fake clock and fault injection |
| Card replacement saga (§6.3/§8.4) | **Real, fully tested** | Partial-failure paths (containment succeeds, shipping fails) exercised directly |
| NLU pipeline (§4) | **Real, substituted, tested** | Stage 0/2 as specced; Stage 1 uses TF-IDF instead of a MiniLM sentence-transformer — see [Substitutions](#substitutions-i-had-to-make) |
| LangGraph orchestration (§5) | **Real, fully tested** | `interrupt()`/`Command(resume=...)` validated against the actually-installed LangGraph 1.2.9, then exercised end-to-end for manual review, user confirmation, and containment |
| FastAPI layer (§14) | **Real, tested** | `TestClient` suite + a real `uvicorn` process hit with `curl` over an actual socket |
| React frontend (§15) | **Real, builds clean** | `npm run build` succeeds; **not** tested against a running backend end-to-end (no browser automation in this environment) |
| Integration adapters (§8.1) | **Mocked, per the doc's own design** | §8.5 explicitly specifies fault-injecting mocks for dev/CI — no real core banking/fraud/fulfillment system exists to integrate with |
| Auth/OIDC (§10.4) | **Stub, dev-only** | `LocalDevAuthService` satisfies the real interface but has a hardcoded dev MFA code — replace before anything resembling production |
| Terraform / K8s (infra/) | **Scaffold only** | Syntactically-reasonable HCL/YAML, **never applied** — no cloud account to apply it against, and `terraform validate` isn't installable in this sandbox (no network access to releases.hashicorp.com) |
| Policy threshold values | **Illustrative, explicitly flagged** | Copied from the doc's own examples; the doc itself says these need Risk/Compliance/Legal sign-off (§0, §7.2) — nothing here changes that |
| PCI DSS / ECOA / OFAC compliance | **Not applicable** | No code makes a system PCI-compliant or satisfies ECOA. This implements the *architecture* the doc specifies for supporting compliance (audit trail, adverse-action reason codes, sanctions-screening hook); actual compliance requires the sign-offs, certifications, and legal review the doc itself defers to Legal/Compliance/Risk in §0 and §10 |

## Substitutions I had to make

**Stage 1 NLU classifier (§4.1).** The doc specifies a MiniLM-class
sentence-transformer or a fine-tuned DistilBERT classifier. Both need
pretrained weights from a model hub; this sandboxed build environment's
network allowlist doesn't include Hugging Face Hub or any model-hub
domain. `app/nlu/embedding_classifier.py` implements the same interface
(`top_k(text) -> ranked candidates`) with TF-IDF + cosine similarity
instead, fit on a small seed corpus in `app/nlu/intents.yaml`. I
calibrated its threshold empirically rather than copying the doc's
illustrative 0.85 — TF-IDF on a ~24-example corpus gives noisier
similarity scores than a real sentence embedding would (a single shared
word was enough to spuriously score 0.48 against a completely unrelated
query in testing), so the threshold is set high (0.75) to push anything
short of a near-exact match to Stage 2's LLM rather than let Stage 1
guess wrong. **Practical effect: more traffic hits the LLM stage than the
doc's design assumes**, until you swap in a real sentence-transformer
(the interface won't need to change — see that file's docstring).

**Per-intent LangGraph subgraphs (§6).** The doc describes each intent
(fee reversal, credit limit, card replacement) as its own mounted
subgraph with named sub-states (`identify_fee → verify_eligibility →
policy_check`, etc.). This implementation folds each flow's data-gathering
into one `policy_check` node, dispatched by intent, rather than building
three separately-checkpointed subgraphs. Behaviorally equivalent for
everything tested here; splitting into real subgraphs is a mechanical
refactor if you need to checkpoint/resume *inside* a flow rather than
only at this node's boundary.

**Fee/entity disambiguation.** §6.1 says "if multiple fees are pending,
present an itemized list and force explicit selection." This reference
build escalates to a human instead of looping back into conversation to
ask — a safe fallback, not the fuller UX the doc describes.

## A design-doc inconsistency I found and resolved

§7.4 defines `Decision` as a `TypedDict`, but §7.2's own pseudocode
constructs it positionally: `Decision("denied", ["ACCOUNT_NOT_ELIGIBLE"])`
— which a plain `TypedDict` can't do. `app/domain/models.py` implements
`Decision` as a frozen dataclass instead, which supports both the §7.2
constructor calls verbatim and the §7.4 field contract (via `.dict()` for
serialization).

Separately, worth knowing as a reviewer: §9.3's own hash computation
(which this implementation follows exactly) does **not** include
`payload` in the hashed fields. This isn't a bug — it's what makes §9.8's
crypto-shredding (destroying a PII key on an erasure request) compatible
with an immutable chain. But it does mean the hash chain doesn't, by
itself, detect tampering with payload contents, only with
actor/decision/reason_codes/sequence. See `app/audit/models.py`'s
docstring.

## Real bugs this test suite caught

Not hypothetical — these actually broke a test, and the fix is explained
in a code comment at the fix site:

1. **Address normalization** (`app/domain/models.py`) — `state`/`postal_code`
   were case-folded but `line1`/`city` weren't, so `"123 Main St"` and
   `"123 MAIN ST"` compared unequal, silently defeating the "is this a new
   address" check in §7.2's card-replacement policy.
2. **SQLite datetime round-trip** (`app/models/orm.py`) — SQLite silently
   drops timezone info on read, so the audit verifier recomputed a
   different hash than what was written for the exact same, untouched
   event — a false tamper-positive on every single event, purely from the
   storage layer. Fixed with a `UTCDateTime` type that normalizes on both
   sides.
3. **Missing unique constraint** — §9.4's DDL specifies
   `UNIQUE(session_id, sequence_no)`; the first draft of the ORM model
   didn't have it, which would've let two concurrent writers to the same
   session silently claim the same sequence number instead of one of them
   failing closed.
4. **Mock design gap** — the card-fulfillment mock originally shared one
   fault injector across both `block_card` and `order_replacement`, making
   it impossible to test "containment succeeds, only shipping fails" —
   exactly the §6.3 scenario the saga exists to handle. Refactored to
   support independent per-operation fault injection.
5. **LangGraph state suspension** — fixed an orchestration issue where 
   suspending a graph execution for manual review (via `interrupt()`) 
   did not correctly bubble the `awaiting_human_review` status to the 
   API layer on subsequent invocations. The API now inspects 
   `snapshot.tasks[0].interrupts` directly to properly handle policy 
   engine decision checkpoints.

## Repository layout

```
backend/app/
  domain/        shared dataclasses (AccountSnapshot, Decision, etc.)
  policy/        the policy engine + versioned config (§7)
  audit/         hash-chained audit trail (§9)
  integrations/  adapter Protocols + mocks + circuit breaker/retry (§8)
  nlu/           3-stage classification pipeline (§4)
  orchestration/ LangGraph state machine + nodes + flows (§5-6)
  escalation/    handoff package + ticketing (§11)
  api/v1/        FastAPI routers
backend/tests/   unit / integration / contract / chaos (§16.1)
backend/scripts/ seed_mock_data.py, verify_audit_chain.py -- both actually run, see above
frontend/        React + Vite chat UI
infra/           docker-compose (usable) + Terraform/K8s (scaffold only)
docs/            ARCHITECTURE, SECURITY, API_CONTRACTS, RUNBOOK
```

## Next steps toward production

None of these can be shortcut by more code, from anyone:

1. Risk/Compliance/Legal sign-off on every numeric threshold in
   `app/policy/config_versions/*.json` (the doc requires this in §0/§7.2;
   the placeholders are marked `ILLUSTRATIVE_PLACEHOLDER`).
2. A real OIDC provider + step-up MFA channel, replacing
   `LocalDevAuthService`.
3. Real adapters for core banking, card fulfillment, and a fraud/OFAC
   screening vendor, implementing the Protocols in
   `app/integrations/base_adapter.py`.
4. A trained risk model with SHAP-style explanations (§7.3), replacing
   the placeholder in `mock_fraud_service.py`.
5. PostgresSaver as the LangGraph checkpointer in production (§5.3) —
   this build defaults to the in-memory checkpointer for zero-setup local
   dev; see `docs/RUNBOOK.md`.
6. Applying the Terraform/K8s scaffolds against a real cloud account and
   actually running `terraform validate`/`plan`.
