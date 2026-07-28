from __future__ import annotations

from app.nlu.entity_extractor import extract_entities


class TestEntityExtractor:
    def test_extracts_requested_limit_for_credit_limit_increase(self):
        entities = extract_entities("can you raise my limit to $10,000", "credit_limit_increase", {})
        assert entities["requested_limit"] == 10000.0

    def test_does_not_overwrite_seed_entities(self):
        entities = extract_entities(
            "raise it to 5000", "credit_limit_increase", {"requested_limit": 9999.0}
        )
        assert entities["requested_limit"] == 9999.0

    def test_no_amount_found_leaves_entities_unchanged(self):
        entities = extract_entities("please increase my limit", "credit_limit_increase", {})
        assert "requested_limit" not in entities

    def test_does_not_extract_amounts_for_other_intents(self):
        # §6.1: execution always uses the system-of-record ledger value,
        # never a number the customer typed -- this only applies to
        # credit_limit_increase's *requested* amount, and even then it's
        # advisory, not authoritative.
        entities = extract_entities("waive the $35 late fee", "fee_reversal", {})
        assert "requested_limit" not in entities
