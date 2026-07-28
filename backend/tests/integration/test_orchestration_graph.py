from __future__ import annotations

from datetime import datetime, timezone

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.audit.writer import AuditTrailWriter
from app.audit.verifier import ChainVerifier
from app.db.session import build_engine, build_session_factory, init_schema
from app.dependencies import build_reference_dependencies
from app.domain.models import AccountSnapshot, AccountStatus, Address, CreditProfile, FeeRecord, RiskScore
from app.nlu.llm_classifier import FakeLLMClassifier
from app.nlu.schemas import IntentClassification
from app.orchestration.graph import build_graph

REPO_ROOT_BACKEND = __import__("pathlib").Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT_BACKEND / "app" / "policy" / "config_versions"
INTENTS_YAML = REPO_ROOT_BACKEND / "app" / "nlu" / "intents.yaml"

ADDRESS = Address(line1="1 Main St", city="Springfield", state_or_province="IL",
                   postal_code="62701", country="US")


def make_graph(fake_llm_responses=None, tmp_path=None):
    engine = build_engine(f"sqlite:///{tmp_path}/orch_test.db")
    init_schema(engine)
    session_factory = build_session_factory(engine)
    audit_writer = AuditTrailWriter(session_factory)
    verifier = ChainVerifier(session_factory)

    deps = build_reference_dependencies(
        policy_config_dir=str(POLICY_DIR), intents_yaml_path=str(INTENTS_YAML),
        llm_classifier=FakeLLMClassifier(fake_llm_responses or []),
    )
    graph = build_graph(deps, audit_writer, InMemorySaver())
    return graph, deps, audit_writer, verifier


def seed_standard_account(deps, account_ref="acct_1", **overrides):
    defaults = dict(
        account_ref=account_ref, status=AccountStatus.ACTIVE, current_limit=5000.0,
        days_past_due=0, recent_nsf_count=0, address_on_file=ADDRESS,
        active_replacement_in_transit=False, card_ref="card_1",
    )
    defaults.update(overrides)
    deps.core_banking.seed_account(AccountSnapshot(**defaults))
    deps.core_banking.seed_credit_profile(CreditProfile(
        account_ref=account_ref, utilization_trend=0.2, payment_history_score=0.9,
        tenure_months=36, recent_inquiries=0,
    ))


def initial_state(session_id, customer_ref, message):
    return {
        "session_id": session_id, "customer_ref": customer_ref, "auth_level": "authenticated",
        "messages": [{"role": "customer", "content": message}], "intent": None, "entities": {},
        "task_queue": [], "clarification_attempts": 0, "decision": None,
        "idempotency_key": None, "escalation_reason": None,
    }


class TestFeeReversalHappyPath:
    def test_auto_approved_fee_reversal_executes_end_to_end(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(tmp_path=tmp_path)
        seed_standard_account(deps)
        deps.core_banking.seed_fee("acct_1", FeeRecord(
            fee_id="fee_1", fee_type="late_fee", amount=35.0, currency="USD",
            posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
        ))

        config = {"configurable": {"thread_id": "sess_1"}}
        state = initial_state("sess_1", "acct_1", "please waive my late fee")
        result = graph.invoke(state, config)

        # Should pause at confirm_with_user (approved decisions still need
        # the explicit UI confirmation click per §15).
        assert "__interrupt__" in result
        assert result["decision"]["outcome"] == "approved"

        result = graph.invoke(Command(resume={"confirmed": True}), config)

        assert "__interrupt__" not in result
        assert result["decision"]["executed"] is True
        assert deps.core_banking.get_fee("acct_1", "fee_1") is None  # actually reversed

        assert verifier.chain_intact("sess_1")
        chain = verifier.verify_session("sess_1")
        assert chain.events_checked >= 5  # auth, classify, policy, confirm, execute, turn-end

    def test_customer_cancels_at_confirmation_nothing_executes(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(tmp_path=tmp_path)
        seed_standard_account(deps)
        deps.core_banking.seed_fee("acct_1", FeeRecord(
            fee_id="fee_1", fee_type="late_fee", amount=35.0, currency="USD",
            posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
        ))

        config = {"configurable": {"thread_id": "sess_cancel"}}
        graph.invoke(initial_state("sess_cancel", "acct_1", "please waive my late fee"), config)
        result = graph.invoke(Command(resume={"confirmed": False}), config)

        assert result["decision"].get("executed") is not True
        assert deps.core_banking.get_fee("acct_1", "fee_1") is not None  # NOT reversed
        assert verifier.chain_intact("sess_cancel")


class TestManualReviewInterruptResume:
    def test_fee_above_ceiling_pauses_for_human_and_resumes_on_approval(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(tmp_path=tmp_path)
        seed_standard_account(deps)
        policy = deps.policy_engine._registry.current("fee_reversal")  # noqa: SLF001 -- test introspection only
        deps.core_banking.seed_fee("acct_1", FeeRecord(
            fee_id="fee_big", fee_type="annual_fee", amount=policy.auto_approval_ceiling_usd + 50,
            currency="USD", posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
        ))

        config = {"configurable": {"thread_id": "sess_review"}}
        result = graph.invoke(
            initial_state("sess_review", "acct_1", "can you dispute this annual fee"), config
        )

        assert "__interrupt__" in result
        state = graph.get_state(config)
        assert state.next == ("policy_check",)
        interrupt_payload = result["__interrupt__"][0].value
        assert interrupt_payload["reason"] == ["EXCEEDS_AUTO_CEILING"]
        assert "handoff_package" in interrupt_payload

        # Human agent reviews and approves via Command(resume=...)
        result = graph.invoke(
            Command(resume={"outcome": "approved", "agent_id": "agent_42", "note": "goodwill approved"}),
            config,
        )

        assert "__interrupt__" in result  # now paused at confirm_with_user instead
        assert result["decision"]["outcome"] == "approved"

        result = graph.invoke(Command(resume={"confirmed": True}), config)
        assert result["decision"]["executed"] is True
        assert deps.core_banking.get_fee("acct_1", "fee_big") is None

        chain = verifier.verify_session("sess_review")
        assert chain.intact
        human_decision_events = [
            e for e in _events_of_type(audit_writer, "sess_review", "human_decision")
        ]
        assert any(e["actor"] == "human:agent_42" for e in human_decision_events)

    def test_human_denies_manual_review_case(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(tmp_path=tmp_path)
        seed_standard_account(deps)
        policy = deps.policy_engine._registry.current("fee_reversal")  # noqa: SLF001
        deps.core_banking.seed_fee("acct_1", FeeRecord(
            fee_id="fee_big", fee_type="annual_fee", amount=policy.auto_approval_ceiling_usd + 50,
            currency="USD", posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
        ))

        config = {"configurable": {"thread_id": "sess_deny"}}
        graph.invoke(initial_state("sess_deny", "acct_1", "can you dispute this annual fee"), config)
        result = graph.invoke(
            Command(resume={"outcome": "denied", "agent_id": "agent_7", "note": "not eligible"}), config
        )

        assert "__interrupt__" not in result  # denied routes straight to audit_log, no confirm needed
        assert result["decision"]["outcome"] == "denied"
        assert deps.core_banking.get_fee("acct_1", "fee_big") is not None  # untouched
        assert verifier.chain_intact("sess_deny")


class TestCardReplacementContainment:
    def test_stolen_card_blocked_unconditionally_before_policy_check(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(
            fake_llm_responses=[
                IntentClassification(intent="card_replacement", entities={"reason": "stolen"}, confidence=0.95)
            ],
            tmp_path=tmp_path,
        )
        seed_standard_account(deps)

        config = {"configurable": {"thread_id": "sess_stolen"}}
        # Deliberately novel phrasing so this reaches the (fake) LLM stage
        # rather than Stage 0's rule match, to prove containment doesn't
        # depend on which NLU stage resolved the intent.
        result = graph.invoke(
            initial_state("sess_stolen", "acct_1", "someone lifted my wallet at the gym"), config
        )

        # Card must already be blocked even though we're still paused
        # waiting on the user's explicit confirmation to *ship* -- the
        # doc is explicit that containment does not wait on confirmation.
        assert deps.card_fulfillment.is_blocked("card_1")
        assert "__interrupt__" in result
        assert result["decision"]["outcome"] == "approved"

        graph.invoke(Command(resume={"confirmed": True}), config)
        assert len(deps.card_fulfillment.shipments_for("acct_1")) == 1
        assert verifier.chain_intact("sess_stolen")

    def test_damaged_card_does_not_trigger_containment(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(tmp_path=tmp_path)
        seed_standard_account(deps)

        config = {"configurable": {"thread_id": "sess_damaged"}}
        graph.invoke(initial_state("sess_damaged", "acct_1", "my card is damaged and won't work"), config)

        assert not deps.card_fulfillment.is_blocked("card_1")


class TestClassifyIntentClarifyLoop:
    def test_ambiguous_then_clarified_resolves(self, tmp_path):
        graph, deps, audit_writer, verifier = make_graph(
            fake_llm_responses=[
                IntentClassification(intent="none", entities={}, confidence=0.1,
                                      top_candidates=["fee_reversal", "card_replacement"]),
                IntentClassification(intent="fee_reversal", entities={"fee_type": "late_fee"}, confidence=0.9),
            ],
            tmp_path=tmp_path,
        )
        seed_standard_account(deps)
        deps.core_banking.seed_fee("acct_1", FeeRecord(
            fee_id="fee_1", fee_type="late_fee", amount=35.0, currency="USD",
            posted_at=datetime.now(timezone.utc), waivers_last_12_months=0,
        ))

        config = {"configurable": {"thread_id": "sess_clarify"}}
        state = initial_state("sess_clarify", "acct_1", "something about my account")
        result = graph.invoke(state, config)

        # The clarify loop itself is not an interrupt -- classify_intent's
        # conditional edge loops back to itself internally within one
        # graph.invoke() call, consuming a second FakeLLMClassifier
        # response, and resolves to fee_reversal on that second attempt.
        # It then correctly *continues* into policy_check -> approved ->
        # confirm_with_user, which *does* interrupt (as it should for any
        # approved action awaiting the explicit confirmation click, §15)
        # -- that's a second, expected pause, not a sign the clarify loop
        # failed.
        assert result["intent"] == "fee_reversal"
        assert "__interrupt__" in result
        assert result["decision"]["outcome"] == "approved"

        result = graph.invoke(Command(resume={"confirmed": True}), config)
        assert result["decision"]["executed"] is True


def _events_of_type(audit_writer: AuditTrailWriter, session_id: str, event_type: str) -> list[dict]:
    from sqlalchemy import select
    from app.models.orm import AuditEventRow

    with audit_writer._session_factory() as db:  # noqa: SLF001 -- test introspection only
        stmt = (
            select(AuditEventRow)
            .where(AuditEventRow.session_id == session_id, AuditEventRow.event_type == event_type)
            .order_by(AuditEventRow.sequence_no.asc())
        )
        rows = db.execute(stmt).scalars().all()
    return [{"actor": r.actor, "payload": r.payload} for r in rows]
