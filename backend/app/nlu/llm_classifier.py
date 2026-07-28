"""Stage 2: LLM structured classifier (§4.1).

Only invoked on ambiguity. Uses tool-calling / structured-output mode so
the response is a typed object, never free text parsed heuristically --
this is what the doc calls out as necessary for multi-intent messages and
novel phrasing (§4.1).

`AnthropicLLMClassifier` requires ANTHROPIC_API_KEY (see app/config.py)
and is not exercised by the test suite -- tests use `FakeLLMClassifier`
below, so the suite runs fully offline and deterministically, with zero
API cost and zero network flakiness in CI.
"""
from __future__ import annotations

import json
from typing import Protocol
from urllib import error, request

from app.nlu.schemas import IntentClassification, SubIntent

KNOWN_INTENTS = ["fee_reversal", "credit_limit_increase", "card_replacement", "none"]

CLASSIFIER_TOOL = {
    "name": "classify_intent",
    "description": "Classify a card-servicing customer message into one or more known intents.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": KNOWN_INTENTS},
            "entities": {"type": "object"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "multi_intent": {"type": "boolean"},
            "sub_intents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"intent": {"type": "string"}, "entities": {"type": "object"}},
                    "required": ["intent"],
                },
            },
            "top_candidates": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["intent", "entities", "confidence"],
    },
}

SYSTEM_PROMPT = (
    "You classify card-servicing chat messages into exactly one of: "
    "fee_reversal, credit_limit_increase, card_replacement, or none. "
    "You never approve, deny, or promise any financial action -- you only "
    "classify and extract entities; a separate deterministic policy engine "
    "makes every actual decision. Always respond by calling the "
    "classify_intent tool; never answer in free text."
)


class LLMClassifier(Protocol):
    def classify(
        self, utterance: str, candidate_intents: list, conversation_context: list
    ) -> IntentClassification: ...


class AnthropicLLMClassifier:
    def __init__(self, client, model: str = "claude-sonnet-5"):
        """`model` defaults to Claude Sonnet 5 for accuracy on the
        genuinely-ambiguous traffic that reaches this stage; swap to a
        smaller/cheaper model (e.g. Claude Haiku 4.5) once volume
        justifies optimizing cost over the last few points of accuracy.
        Re-check current model names/pricing at docs.claude.com before
        deploying -- both evolve."""
        self._client = client
        self._model = model

    def classify(
        self, utterance: str, candidate_intents: list, conversation_context: list
    ) -> IntentClassification:
        context_str = "\n".join(
            f"{m.get('role')}: {m.get('content')}" for m in conversation_context
        )
        message = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            tools=[CLASSIFIER_TOOL],
            tool_choice={"type": "tool", "name": "classify_intent"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Candidate intents from the embedding stage: {candidate_intents}\n"
                        f"Recent conversation:\n{context_str}\n\n"
                        f"Latest customer message: {utterance}"
                    ),
                }
            ],
        )
        tool_use = next(b for b in message.content if b.type == "tool_use")
        return self._parse(dict(tool_use.input))

    @staticmethod
    def _parse(data: dict) -> IntentClassification:
        sub_intents = [
            SubIntent(intent=s["intent"], entities=s.get("entities", {}))
            for s in data.get("sub_intents", [])
        ]
        return IntentClassification(
            intent=data["intent"],
            entities=data.get("entities", {}),
            confidence=float(data["confidence"]),
            multi_intent=bool(data.get("multi_intent", False)),
            sub_intents=sub_intents,
            top_candidates=data.get("top_candidates", []),
        )


class GroqLLMClassifier:
    def __init__(self, api_key: str, model: str = "llama-3.1-8b-instant"):
        self._api_key = api_key
        self._model = model
        self._endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def classify(
        self, utterance: str, candidate_intents: list, conversation_context: list
    ) -> IntentClassification:
        context_str = "\n".join(
            f"{m.get('role')}: {m.get('content')}" for m in conversation_context
        )
        prompt = (
            "You are a classifier for card-servicing customer requests. "
            "Only output valid JSON with the fields: intent, entities, confidence, "
            "multi_intent, sub_intents, and top_candidates. "
            "Do not output any explanation text.\n\n"
            f"Candidate intents: {candidate_intents}\n"
            f"Recent conversation:\n{context_str}\n\n"
            f"Latest customer message: {utterance}\n"
        )

        body = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }).encode("utf-8")
        req = request.Request(
            self._endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )

        try:
            with request.urlopen(req, timeout=30) as res:
                payload = json.loads(res.read().decode())
        except error.HTTPError as exc:
            raise RuntimeError(f"Groq API request failed: {exc.code} {exc.reason} - {exc.read().decode()}")

        text = payload["choices"][0]["message"]["content"]
        json_text = self._extract_json(text)
        parsed = json.loads(json_text)
        return self._parse(parsed)

    @staticmethod
    def _extract_json(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Groq response did not contain valid JSON")
        return text[start : end + 1]

    @staticmethod
    def _parse(data: dict) -> IntentClassification:
        sub_list = data.get("sub_intents") or []
        sub_intents = []
        for s in sub_list:
            if isinstance(s, dict) and "intent" in s:
                sub_intents.append(SubIntent(intent=s["intent"], entities=s.get("entities", {}) if isinstance(s.get("entities"), dict) else {}))
            elif isinstance(s, str):
                sub_intents.append(SubIntent(intent=s, entities={}))
        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {}
        return IntentClassification(
            intent=data["intent"],
            entities=entities,
            confidence=float(data.get("confidence", 0.0)),
            multi_intent=bool(data.get("multi_intent", False)),
            sub_intents=sub_intents,
            top_candidates=data.get("top_candidates", []),
        )


class FakeLLMClassifier:
    """Deterministic stand-in for tests and offline development. Returns a
    scripted response queue so orchestration/flow tests can exercise the
    clarify/escalate/multi-intent branches without network access or an
    API key."""

    def __init__(self, responses: list | None = None):
        self._responses = list(responses or [])
        self.calls: list[dict] = []

    def classify(
        self, utterance: str, candidate_intents: list, conversation_context: list
    ) -> IntentClassification:
        self.calls.append({
            "utterance": utterance,
            "candidate_intents": candidate_intents,
            "conversation_context": conversation_context,
        })
        if self._responses:
            return self._responses.pop(0)
        return IntentClassification(
            intent="none", entities={}, confidence=0.0, top_candidates=candidate_intents
        )
