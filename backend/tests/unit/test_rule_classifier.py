from __future__ import annotations

from app.nlu.rule_classifier import RuleClassifier


class TestRuleClassifier:
    def setup_method(self):
        self.classifier = RuleClassifier()

    def test_matches_fee_reversal_with_fee_type_entity(self):
        match = self.classifier.match("can you waive my late fee")
        assert match is not None
        assert match.intent == "fee_reversal"
        assert match.entities == {"fee_type": "late_fee"}
        assert match.confidence >= 0.9

    def test_matches_credit_limit_increase(self):
        match = self.classifier.match("I want to increase my credit limit")
        assert match is not None
        assert match.intent == "credit_limit_increase"

    def test_matches_card_replacement_with_reason_entity(self):
        match = self.classifier.match("my card was stolen yesterday")
        assert match is not None
        assert match.intent == "card_replacement"
        assert match.entities == {"reason": "stolen"}

    def test_returns_none_for_unrelated_text(self):
        match = self.classifier.match("what's the weather like today")
        assert match is None

    def test_returns_none_for_genuinely_ambiguous_text(self):
        # No unambiguous keyword combination -- should fall through to
        # Stage 1/2 rather than guess.
        match = self.classifier.match("I have a question about my account")
        assert match is None
