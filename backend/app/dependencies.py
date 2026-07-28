"""Bundles the collaborators orchestration nodes close over, so node
factory functions take one `deps` object rather than an ever-growing
argument list as more integrations are added.

`build_reference_dependencies()` wires the mock adapters (§8.5) together
into a working system with zero external requirements -- this is what
local dev, the test suite, and `scripts/seed_mock_data.py` all use.
Swapping to real backends means writing real adapters that satisfy the
same Protocols in `app/integrations/base_adapter.py` and constructing a
different `Dependencies` instance; nothing in `app/orchestration` needs
to change.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.security import AuthService, LocalDevAuthService
from app.escalation.ticketing_adapter import MockTicketingAdapter
from app.integrations.base_adapter import (
    CardFulfillmentAdapter,
    CoreBankingAdapter,
    FraudServiceAdapter,
    NotificationAdapter,
)
from app.integrations.mocks.mock_card_fulfillment import MockCardFulfillmentAdapter
from app.integrations.mocks.mock_core_banking import MockCoreBankingAdapter
from app.integrations.mocks.mock_fraud_service import MockFraudServiceAdapter
from app.integrations.mocks.mock_notification import MockNotificationAdapter
from app.nlu.embedding_classifier import EmbeddingClassifier
from app.nlu.llm_classifier import FakeLLMClassifier, LLMClassifier
from app.nlu.pipeline import NLUPipeline
from app.nlu.rule_classifier import RuleClassifier
from app.orchestration.flows.card_replacement_flow import CardReplacementSaga
from app.policy.config import PolicyRegistry
from app.policy.engine import PolicyEngine


@dataclass
class Dependencies:
    nlu: NLUPipeline
    policy_engine: PolicyEngine
    core_banking: CoreBankingAdapter
    card_fulfillment: CardFulfillmentAdapter
    fraud_service: FraudServiceAdapter
    notification: NotificationAdapter
    card_replacement_saga: CardReplacementSaga
    auth_service: AuthService
    ticketing: MockTicketingAdapter


def build_reference_dependencies(
    policy_config_dir: str,
    intents_yaml_path: str,
    llm_classifier: LLMClassifier | None = None,
) -> Dependencies:
    core_banking = MockCoreBankingAdapter()
    fraud_service = MockFraudServiceAdapter()
    notification = MockNotificationAdapter()
    card_fulfillment = MockCardFulfillmentAdapter(core_banking=core_banking)

    nlu = NLUPipeline(
        rule_classifier=RuleClassifier(),
        embedding_classifier=EmbeddingClassifier.from_intents_yaml(intents_yaml_path),
        llm_classifier=llm_classifier or FakeLLMClassifier(),
    )
    policy_engine = PolicyEngine(
        registry=PolicyRegistry.from_directory(policy_config_dir),
        sanctions_screener=fraud_service,
    )
    saga = CardReplacementSaga(card_fulfillment)

    return Dependencies(
        nlu=nlu, policy_engine=policy_engine, core_banking=core_banking,
        card_fulfillment=card_fulfillment, fraud_service=fraud_service, notification=notification,
        card_replacement_saga=saga, auth_service=LocalDevAuthService(), ticketing=MockTicketingAdapter(),
    )
