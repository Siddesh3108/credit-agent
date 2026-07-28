from __future__ import annotations

from app.core.pii_redaction import mask_card_number, redact_pii


class TestRedactPii:
    def test_redacts_ssn(self):
        result = redact_pii("my ssn is 123-45-6789 please help")
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_redacts_valid_luhn_card_number(self):
        # 4111111111111111 is a well-known publicly-documented Visa TEST
        # card number (not a real cardholder's card) used industry-wide
        # for exactly this kind of test.
        result = redact_pii("my card number is 4111111111111111 ok")
        assert "4111111111111111" not in result
        assert "[CARD_NUMBER_REDACTED]" in result

    def test_does_not_redact_invalid_luhn_number_sequences(self):
        # A 16-digit sequence that fails the Luhn check (e.g. a random
        # order/reference number) should not be flagged as a card number.
        text = "order reference 1234567890123456"
        result = redact_pii(text)
        assert result == text

    def test_leaves_ordinary_text_unchanged(self):
        text = "can you waive my late fee please"
        assert redact_pii(text) == text


class TestMaskCardNumber:
    def test_masks_all_but_last_four(self):
        assert mask_card_number("4111111111111111") == "************1111"

    def test_handles_spaced_input(self):
        assert mask_card_number("4111 1111 1111 1111") == "************1111"

    def test_short_input_fully_masked(self):
        assert mask_card_number("12") == "**"
