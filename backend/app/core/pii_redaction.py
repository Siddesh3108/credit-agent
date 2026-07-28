"""§10.5's redaction middleware + §10.3's mask_card_number utility.

`redact_pii` is a defense-in-depth text filter, not the primary control --
the primary control is that the LLM is never handed a full account record
to begin with (Principle 6, §2; §10.5's "Excessive context exposure"
mitigation). Treat this as a safety net, not the only net.
"""
from __future__ import annotations

import re

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_valid(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact_pii(text: str) -> str:
    """Strips Tier 0/1 PII patterns before anything reaches an LLM (§10.5,
    and §4.2's `redact_pii` call at the top of `classify_and_route`)."""
    redacted = _SSN_RE.sub("[SSN_REDACTED]", text)

    def _maybe_redact_card(match: "re.Match") -> str:
        candidate = match.group(0)
        digits_only = re.sub(r"[ -]", "", candidate)
        if len(digits_only) >= 13 and _luhn_valid(digits_only):
            return "[CARD_NUMBER_REDACTED]"
        return candidate

    redacted = _CARD_CANDIDATE_RE.sub(_maybe_redact_card, redacted)
    return redacted


def mask_card_number(pan: str) -> str:
    """Shared mask utility used at every serialization boundary (§10.3):
    anywhere a card number must be displayed, only the last 4 digits are
    shown."""
    digits = re.sub(r"\D", "", pan)
    if len(digits) < 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"
