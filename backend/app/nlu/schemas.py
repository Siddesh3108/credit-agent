from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubIntent:
    intent: str
    entities: dict = field(default_factory=dict)


@dataclass
class IntentClassification:
    intent: str
    entities: dict
    confidence: float
    multi_intent: bool = False
    sub_intents: list = field(default_factory=list)
    top_candidates: list = field(default_factory=list)
