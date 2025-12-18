from __future__ import annotations

import re
from typing import Iterable


# Basic PII patterns: phone, email, 9+ digit numbers (SSN-like), and cards (13-19 digits).
_PHONE_RE = re.compile(r"(?<![0-9A-Za-z])\+?\d(?:[\d\-\s\(\)]*\d){9,}(?![0-9A-Za-z])")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SSN_RE = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_CARD_RE = re.compile(r"\b\d{13,19}\b")


def mask_value(value: str, mask_char: str = "•") -> str:
    """Mask all but last 2 characters of a string."""
    clean = value.strip()
    if len(clean) <= 2:
        return mask_char * len(clean)
    return mask_char * (len(clean) - 2) + clean[-2:]


def redact_text(text: str) -> str:
    """Redact likely PII from free-form text."""
    if not text:
        return text
    redacted = text
    for regex in (_EMAIL_RE, _PHONE_RE, _SSN_RE, _CARD_RE):
        redacted = regex.sub(lambda m: mask_value(m.group(0)), redacted)
    return redacted


def redact_iter(items: Iterable[str | None]) -> list[str]:
    """Redact each string in an iterable, skipping None."""
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        out.append(redact_text(str(item)))
    return out
