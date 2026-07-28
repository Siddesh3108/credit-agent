"""Implements §4.2's `classify_and_route` algorithm: Stage 0 (rules) ->
Stage 1 (embeddings) -> Stage 2 (LLM structured classifier) -> clarify
once -> escalate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.pii_redaction import redact_pii
from app.nlu.embedding_classifier import EmbeddingClassifier
from app.nlu.entity_extractor import extract_entities
from app.nlu.llm_classifier import LLMClassifier
from app.nlu.rule_classifier import RuleClassifier

RULE_THRESHOLD = 0.90
# TF-IDF cosine similarity, not a sentence-embedding score -- calibrated
# empirically against this repo's tiny (~8 examples/intent) seed corpus,
# not copied from the doc's illustrative 0.85. Measured behavior: a
# near-verbatim match to a seed example scores 1.0; genuine paraphrases
# that share little vocabulary with the seeds (e.g. "my card is broken
# and stopped working" vs. seed "my card is damaged and won't work")
# score as low as 0.35 and can even rank the wrong intent highest, because
# a single shared word in a tiny corpus carries outsized weight (a
# spurious 0.48 for a totally unrelated query was observed before this
# was raised from an initially-chosen 0.30). Set high enough that Stage 1
# only resolves near-exact matches and defers everything else to Stage
# 2's LLM -- this pushes more traffic to the LLM stage than the doc's
# MiniLM-based design would need, which is the real cost of the
# substitution documented in embedding_classifier.py.
EMBED_THRESHOLD = 0.75
LLM_THRESHOLD = 0.70
MAX_CLARIFICATION_ATTEMPTS = 1


@dataclass
class ClassificationResult:
    status: Literal["resolved", "clarify", "escalate"]
    intent: str | None = None
    entities: dict = field(default_factory=dict)
    stage: str | None = None
    confidence: float | None = None
    candidates: list = field(default_factory=list)
    extra_intents: list = field(default_factory=list)
    reason: str | None = None


class NLUPipeline:
    def __init__(
        self,
        rule_classifier: RuleClassifier,
        embedding_classifier: EmbeddingClassifier,
        llm_classifier: LLMClassifier,
    ):
        self._rules = rule_classifier
        self._embeddings = embedding_classifier
        self._llm = llm_classifier

    def classify(self, utterance: str, session: dict) -> ClassificationResult:
        redacted = redact_pii(utterance)

        # Stage 0
        rule_match = self._rules.match(redacted)
        if rule_match and rule_match.confidence >= RULE_THRESHOLD:
            entities = extract_entities(redacted, rule_match.intent, rule_match.entities)
            return ClassificationResult(
                status="resolved", intent=rule_match.intent, entities=entities,
                stage="rule", confidence=rule_match.confidence,
            )

        # Stage 1
        top_candidates = self._embeddings.top_k(redacted, k=3)
        if top_candidates and top_candidates[0].score >= EMBED_THRESHOLD:
            top = top_candidates[0]
            entities = extract_entities(redacted, top.intent, {})
            return ClassificationResult(
                status="resolved", intent=top.intent, entities=entities,
                stage="embedding", confidence=top.score,
            )

        # Stage 2 -- ambiguous or novel phrasing
        result = self._llm.classify(
            utterance=redacted,
            candidate_intents=[c.intent for c in top_candidates],
            conversation_context=session.get("messages", [])[-6:],
        )

        if result.multi_intent and result.sub_intents:
            first, *rest = result.sub_intents
            return ClassificationResult(
                status="resolved", intent=first.intent, entities=first.entities,
                stage="llm", confidence=result.confidence,
                extra_intents=[{"intent": s.intent, "entities": s.entities} for s in rest],
            )

        if result.intent != "none" and result.confidence >= LLM_THRESHOLD:
            return ClassificationResult(
                status="resolved", intent=result.intent, entities=result.entities,
                stage="llm", confidence=result.confidence,
            )

        # Stage 3 -- disambiguate, once
        if session.get("clarification_attempts", 0) < MAX_CLARIFICATION_ATTEMPTS:
            candidates = result.top_candidates or [c.intent for c in top_candidates]
            return ClassificationResult(status="clarify", candidates=candidates, stage="llm")

        return ClassificationResult(status="escalate", reason="unresolved_intent_ambiguity")
