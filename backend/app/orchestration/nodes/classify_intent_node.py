"""classify_intent node (§5.2), wrapping NLUPipeline (§4.2).

Every classification decision is logged with its stage, confidence, and
intent (§4.4's continuous-improvement feedback set) -- this is what a
retraining/prompt-refinement job would read from later.
"""
from __future__ import annotations

from typing import Callable

from app.nlu.pipeline import NLUPipeline
from app.orchestration.state import ConversationState


def make_classify_intent_node(nlu: NLUPipeline, audit_writer) -> Callable[[ConversationState], dict]:
    def classify_intent_node(state: ConversationState) -> dict:
        last_user_message = next(
            (m["content"] for m in reversed(state["messages"]) if m.get("role") == "customer"),
            "",
        )
        result = nlu.classify(last_user_message, dict(state))

        audit_writer.append(
            session_id=state["session_id"], actor="agent_llm", event_type="intent_classified",
            payload={
                "stage": result.stage, "intent": result.intent, "confidence": result.confidence,
                "status": result.status,
            },
        )

        if result.status == "resolved":
            merged_entities = result.entities
            if result.intent == state.get("intent"):
                merged_entities = {**(state.get("entities") or {}), **result.entities}
            update: dict = {"intent": result.intent, "entities": merged_entities}
            if result.extra_intents:
                update["task_queue"] = [*state.get("task_queue", []), *result.extra_intents]
            return update

        if result.status == "clarify":
            return {"clarification_attempts": state.get("clarification_attempts", 0) + 1}

        return {"escalation_reason": result.reason or "unresolved_intent_ambiguity"}

    return classify_intent_node
