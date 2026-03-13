"""
Unit tests for safety utilities — PII redaction and validation.
"""
import pytest

from app.utils.safety import redact_pii, redact_profanity, validate_question


class TestRedactPII:
    def test_redacts_email(self):
        result = redact_pii("Contact me at alice@example.com please")
        assert "[EMAIL_REDACTED]" in result
        assert "alice@example.com" not in result

    def test_redacts_ssn(self):
        result = redact_pii("My SSN is 123-45-6789")
        assert "[SSN_REDACTED]" in result
        assert "123-45-6789" not in result

    def test_preserves_normal_text(self):
        text = "What is the deployment process?"
        assert redact_pii(text) == text


class TestRedactProfanity:
    def test_redacts_profanity(self):
        result = redact_profanity("What the hell is this?")
        assert "hell" not in result
        assert "****" in result

    def test_preserves_clean_text(self):
        text = "How do I install the software?"
        assert redact_profanity(text) == text


class TestValidateQuestion:
    def test_valid_question(self):
        assert validate_question("How do I deploy?") is None

    def test_empty_question(self):
        assert validate_question("") is not None
        assert validate_question("   ") is not None

    def test_too_long_question(self):
        assert validate_question("x" * 2001) is not None

    def test_max_length_ok(self):
        assert validate_question("x" * 2000) is None
