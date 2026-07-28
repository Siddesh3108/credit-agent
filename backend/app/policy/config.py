"""Versioned, config-driven policy thresholds (Principle 5, §2).

Every numeric threshold in the source design doc is explicitly called out
as an engineering default, not a compliance ruling (§0): "Treat every
numeric constant in this doc as config, not code." This module is what
makes that literally true -- thresholds live in versioned JSON files
under `policy/config_versions/`, never as a literal in a rules file.

In production this would read from the `policy_versions` Postgres table
(§13); `PolicyRegistry.from_directory` reads the same shape from disk so
the whole system runs without a database for local dev/tests. Swap the
classmethod used at startup (see app/dependencies.py) to point at
Postgres without touching any rule function.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PolicyConfig:
    version_id: str
    intent: str
    effective_from: datetime
    approved_by: str
    ruleset: dict
    git_commit_sha: str = "unknown"

    @property
    def display_name(self) -> str:
        return f"{self.intent}@{self.version_id}"

    def __getattr__(self, item: str) -> Any:
        # Lets rule code read `policy.max_waivers_per_rolling_year` straight
        # off the versioned ruleset dict, so adding a new threshold never
        # requires touching this class -- only the config file (Principle 5).
        # __getattr__ only fires for names not already found as a normal
        # attribute/dataclass field, so `self.ruleset` itself resolves
        # through the ordinary path, not recursively through here.
        ruleset = object.__getattribute__(self, "ruleset")
        try:
            return ruleset[item]
        except KeyError as exc:
            raise AttributeError(
                f"{item!r} not found on PolicyConfig and not a key in "
                f"ruleset for {self.intent}@{self.version_id}"
            ) from exc


class PolicyRegistry:
    """Resolves "what rule was in effect when this decision was made" (§7.2)."""

    def __init__(self, configs: list[PolicyConfig]):
        self._by_intent: dict[str, list[PolicyConfig]] = {}
        for cfg in configs:
            self._by_intent.setdefault(cfg.intent, []).append(cfg)
        for versions in self._by_intent.values():
            versions.sort(key=lambda c: c.effective_from)

    @classmethod
    def from_directory(cls, directory: str | Path) -> "PolicyRegistry":
        configs = []
        for path in sorted(Path(directory).glob("*.json")):
            data = json.loads(path.read_text())
            data = dict(data)
            data["effective_from"] = datetime.fromisoformat(data["effective_from"])
            configs.append(PolicyConfig(**data))
        if not configs:
            raise FileNotFoundError(f"no policy config JSON files found in {directory}")
        return cls(configs)

    def current(self, intent: str, at: datetime | None = None) -> PolicyConfig:
        at = at or datetime.now(timezone.utc)
        versions = self._by_intent.get(intent, [])
        eligible = [c for c in versions if c.effective_from <= at]
        if not eligible:
            raise LookupError(
                f"no effective policy version for intent={intent!r} at {at.isoformat()}"
            )
        return eligible[-1]

    def all_versions(self, intent: str) -> list[PolicyConfig]:
        return list(self._by_intent.get(intent, []))
