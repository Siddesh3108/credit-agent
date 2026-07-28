"""In-memory stand-in for the fraud/risk service (§8.5).

Important: `is_sanctioned_destination` here does NOT ship with any real
sanctioned-country/entity list. Hardcoding an "OFAC list" in a reference
repo is worse than useless -- it would go stale immediately and could give
a false sense of compliance coverage if someone deployed it as-is. This
mock's screening set starts empty and is meant to be seeded by tests with
obviously-fake data (see `seed_sanctioned_country`). Before production,
`FraudServiceAdapter.is_sanctioned_destination` must be backed by a real
OFAC/sanctions-list vendor (e.g. a screening API), not this mock -- see
docs/SECURITY.md's compliance checklist.
"""
from __future__ import annotations

import random

from app.domain.models import Address, RiskScore


class MockFraudServiceAdapter:
    def __init__(self, rng: random.Random | None = None):
        self._sanctioned_countries: set[str] = set()
        self._risk_overrides: dict[str, RiskScore] = {}
        self._velocity_events: dict[str, list[str]] = {}
        self._rng = rng or random.Random()

    # -- seeding (test/dev only) -------------------------------------
    def seed_sanctioned_country(self, iso2_country_code: str) -> None:
        self._sanctioned_countries.add(iso2_country_code.upper())

    def seed_risk_score(self, account_ref: str, score: RiskScore) -> None:
        self._risk_overrides[account_ref] = score

    # -- FraudServiceAdapter Protocol ----------------------------------
    def score_risk(self, account_ref: str) -> RiskScore:
        if account_ref in self._risk_overrides:
            return self._risk_overrides[account_ref]
        # Deterministic-ish placeholder so unseeded accounts don't crash
        # local dev flows; §7.3 requires a real gradient-boosted/logistic
        # model with SHAP-style explanations in production, not this.
        return RiskScore(probability_of_default=0.02, top_features=(("placeholder", 1.0),))

    def is_sanctioned_destination(self, address: Address) -> bool:
        return address.country in self._sanctioned_countries

    def flag_velocity(self, account_ref: str, event_type: str) -> bool:
        """§10.7: multiple replacement/fee-reversal requests in a short
        window are flagged even if each individually passes policy. This
        in-memory version tracks event counts per-process only -- a real
        implementation needs a shared, time-windowed store (e.g. Redis)
        across all backend replicas."""
        events = self._velocity_events.setdefault(account_ref, [])
        events.append(event_type)
        same_type_count = sum(1 for e in events if e == event_type)
        return same_type_count >= 3
