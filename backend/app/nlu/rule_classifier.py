"""Stage 0: deterministic fast path (§4.1).

Regex/keyword rules for unambiguous phrasing. Zero LLM cost, sub-50ms.
Rules are intentionally conservative -- a false positive here skips both
cheaper-confidence stages, so patterns favor precision over recall.
Ambiguous phrasing is expected to fall through to Stage 1/2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class RuleMatch:
    intent: str
    confidence: float
    entities: dict = field(default_factory=dict)


@dataclass
class _Rule:
    intent: str
    pattern: "re.Pattern"
    entity_fn: Optional[Callable[[str], dict]] = None


def _fee_type_entity(text: str) -> dict:
    if re.search(r"\blate fee\b", text, re.I):
        return {"fee_type": "late_fee"}
    if re.search(r"\bannual fee\b", text, re.I):
        return {"fee_type": "annual_fee"}
    if re.search(r"\b(foreign transaction|fx)\s*fee\b", text, re.I):
        return {"fee_type": "foreign_transaction_fee"}
    return {}


def _replacement_reason_entity(text: str) -> dict:
    if re.search(r"\bstolen\b", text, re.I):
        return {"reason": "stolen"}
    if re.search(r"\blost\b", text, re.I):
        return {"reason": "lost"}
    if re.search(r"\bdamag", text, re.I):
        return {"reason": "damaged"}
    if re.search(r"\bexpir", text, re.I):
        return {"reason": "expiring"}
    if re.search(r"\bname change|new name\b", text, re.I):
        return {"reason": "name_change"}
    return {}


class RuleClassifier:
    def __init__(self, rules: list[_Rule] | None = None):
        self._rules = rules or self._default_rules()

    @staticmethod
    def _default_rules() -> list[_Rule]:
        return [
            _Rule(
                "fee_reversal",
                re.compile(
                    r"\b(waive|reverse|refund|dispute)\b.*\bfee\b|\bfee\b.*\b(waive|reverse|refund)\b",
                    re.I,
                ),
                _fee_type_entity,
            ),
            _Rule(
                "credit_limit_increase",
                re.compile(r"\b(increase|raise|higher|bump up|up my)\b.*\b(credit\s*limit|limit)\b", re.I),
            ),
            _Rule(
                "card_replacement",
                re.compile(
                    r"\b(lost|stolen|damaged|broken|replace|replacement)\b.*\bcard\b|\bcard\b.*\b(lost|stolen|damaged)\b",
                    re.I,
                ),
                _replacement_reason_entity,
            ),
        ]

    def match(self, text: str) -> RuleMatch | None:
        for rule in self._rules:
            if rule.pattern.search(text):
                entities = rule.entity_fn(text) if rule.entity_fn else {}
                return RuleMatch(intent=rule.intent, confidence=0.95, entities=entities)
        return None
