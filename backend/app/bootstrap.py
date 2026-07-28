"""Full application wiring for the FastAPI app (as opposed to
`app/dependencies.py`, which wires just the NLU/policy/adapter layer used
by the orchestration nodes). Kept separate so tests can use
`build_reference_dependencies` directly against an in-memory checkpointer
without booting a whole app.
"""
from __future__ import annotations

from dataclasses import dataclass

from langgraph.checkpoint.memory import InMemorySaver

from app.audit.verifier import ChainVerifier
from app.audit.writer import AuditTrailWriter
from app.config import Settings
from app.db.session import build_engine, build_session_factory, init_schema
from app.dependencies import Dependencies, build_reference_dependencies
from app.nlu.llm_classifier import AnthropicLLMClassifier, FakeLLMClassifier, GroqLLMClassifier
from app.orchestration.graph import build_graph


@dataclass
class AppState:
    settings: Settings
    deps: Dependencies
    audit_writer: AuditTrailWriter
    verifier: ChainVerifier
    graph: object
    session_factory: any
    auth_tokens: dict  # token -> {customer_ref, conversation_id} -- see api/v1/conversations.py


def build_app_state(settings: Settings) -> AppState:
    engine = build_engine(settings.database_url)
    init_schema(engine, app_role=settings.app_write_role)
    session_factory = build_session_factory(engine)
    audit_writer = AuditTrailWriter(session_factory)
    verifier = ChainVerifier(session_factory)

    llm_classifier = None
    if settings.groq_api_key:
        llm_classifier = GroqLLMClassifier(
            api_key=settings.groq_api_key, model=settings.groq_model,
        )
    elif settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        llm_classifier = AnthropicLLMClassifier(client, model=settings.llm_model)
    else:
        # Without a real API key, Stage 2 can't call a live LLM. FakeLLMClassifier
        # is the safe zero-cost fallback used for offline local development.
        llm_classifier = FakeLLMClassifier()

    deps = build_reference_dependencies(
        policy_config_dir=settings.policy_config_dir,
        intents_yaml_path=settings.intents_yaml_path,
        llm_classifier=llm_classifier,
    )

    # NOTE: production needs a *durable* checkpointer (PostgresSaver, per
    # §5.3) so a paused conversation survives a pod restart. This
    # reference build defaults to LangGraph's in-memory checkpointer so
    # `uvicorn app.main:app` works with zero setup; see
    # docs/RUNBOOK.md for the PostgresSaver wiring (identical to §5.3's
    # code sample) and why it isn't the default here.
    checkpointer = InMemorySaver()
    graph = build_graph(deps, audit_writer, checkpointer)

    return AppState(
        settings=settings, deps=deps, audit_writer=audit_writer, verifier=verifier,
        graph=graph, session_factory=session_factory, auth_tokens={},
    )
