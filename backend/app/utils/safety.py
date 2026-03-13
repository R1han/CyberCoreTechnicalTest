"""
Ask-Docs — Safety Utilities

Input validation, PII redaction stub, and profanity filter stub.
"""
from __future__ import annotations

import re

# ── PII redaction patterns (basic stubs) ─────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# Simple profanity word list (stub — extend or replace with a library)
_PROFANITY_WORDS = {
    "damn", "hell",  # intentionally minimal; extend as needed
}
_PROFANITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _PROFANITY_WORDS) + r")\b",
    re.IGNORECASE,
)


def redact_pii(text: str) -> str:
    """Replace common PII patterns with redaction tokens."""
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = _SSN_RE.sub("[SSN_REDACTED]", text)
    text = _CREDIT_CARD_RE.sub("[CARD_REDACTED]", text)
    return text


def redact_profanity(text: str) -> str:
    """Replace profanity with asterisks (stub)."""
    return _PROFANITY_RE.sub(lambda m: "*" * len(m.group()), text)


def validate_question(question: str) -> str | None:
    """
    Return an error message if the question is invalid, else None.
    """
    if not question or not question.strip():
        return "Question must not be empty."
    if len(question) > 2000:
        return "Question exceeds maximum length of 2000 characters."
    return None
