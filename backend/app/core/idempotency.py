"""§8.2: idempotency keys derived from (session_id, node_name, attempt_seed)."""
from __future__ import annotations

import hashlib


def make_idempotency_key(session_id: str, node_name: str, attempt_seed: str) -> str:
    raw = f"{session_id}:{node_name}:{attempt_seed}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
