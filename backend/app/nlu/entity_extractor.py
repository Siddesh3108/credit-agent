"""Lightweight rule-based entity extraction layered on top of whatever a
rule/embedding match already found (§4.2's `extract_entities_ner`).

Deliberately conservative: this never invents a dollar amount to act on --
§6.1 is explicit that execution always uses the system-of-record ledger
value, never a number the customer typed. Anything extracted here is for
routing/display only, never for the amount actually reversed/approved.
"""
from __future__ import annotations

import re

_AMOUNT_RE = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)")


def extract_entities(text: str, intent: str, seed_entities: dict) -> dict:
    entities = dict(seed_entities)

    if intent == "credit_limit_increase" and "requested_limit" not in entities:
        match = _AMOUNT_RE.search(text)
        if match:
            try:
                entities["requested_limit"] = float(match.group(1).replace(",", ""))
            except ValueError:
                pass

    return entities
