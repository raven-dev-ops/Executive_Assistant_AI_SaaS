from __future__ import annotations

from typing import Optional
import logging
import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

"""Lightweight NLU helpers for the Phase 1 conversation manager.

These helpers are intentionally simple and deterministic so they can be used
in safety-critical flows without introducing external dependencies.
"""


def parse_name(text: str) -> Optional[str]:
    """Best-effort extraction of a caller name from free-form input.

    Handles simple lead-in phrases such as "my name is Jane Doe" or "this is
    John" and falls back to treating reasonably short phrases as names.
    """
    stripped = (text or "").strip()
    if not stripped:
        return None

    lower = stripped.lower()
    prefixes = [
        "my name is",
        "this is",
        "i am",
        "i'm",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            candidate = stripped[len(prefix) :].strip(" ,.")
            if candidate:
                return candidate

    # Fallback: treat short phrases with at least one space as names.
    if 0 < len(stripped) <= 40 and any(ch.isspace() for ch in stripped):
        return stripped

    return None


def parse_address(text: str) -> Optional[str]:
    """Best-effort extraction of a street-style address.

    This is deliberately tolerant but still conservative:
    - requires at least one digit (street number or ZIP code)
    - accepts common street suffixes or a comma-separated structure
    - accepts presence of a 5-digit ZIP even if suffix is missing
    """
    stripped = (text or "").strip()
    if not stripped:
        return None

    lower = stripped.lower()
    if not any(ch.isdigit() for ch in stripped):
        return None

    suffixes = {
        " st",
        " street",
        " ave",
        " avenue",
        " rd",
        " road",
        " blvd",
        " boulevard",
        " dr",
        " drive",
        " ln",
        " lane",
        " ct",
        " court",
        " hwy",
        " highway",
        " pkwy",
        " parkway",
        " ter",
        " terrace",
        " pl",
        " place",
    }
    has_suffix = any(suffix in lower for suffix in suffixes)
    has_comma = "," in stripped
    has_zip = any(ch.isdigit() for ch in stripped[-5:]) and any(
        part.isdigit() and len(part) == 5 for part in stripped.replace(",", " ").split()
    )
    looks_like_street_number = stripped[0].isdigit()

    if not (has_suffix or has_comma or has_zip or looks_like_street_number):
        return None

    # Normalize whitespace/punctuation lightly.
    normalized = " ".join(stripped.replace(" ,", ",").split())
    return normalized


INTENT_LABELS = [
    "emergency",
    "schedule",
    "reschedule",
    "cancel",
    "faq",
    "greeting",
    "other",
]


def _heuristic_intent(text: str) -> str:
    """Deterministic, keyword-driven intent classifier."""
    lower = (text or "").lower()
    if not lower:
        return "greeting"
    if any(k in lower for k in ["burst", "flood", "sewage", "gas leak", "no water"]):
        return "emergency"
    if any(k in lower for k in ["cancel", "canceling", "cancelling"]):
        return "cancel"
    if "resched" in lower or "change my time" in lower:
        return "reschedule"
    if any(k in lower for k in ["book", "schedule", "appointment", "available", "tomorrow"]):
        return "schedule"
    if any(k in lower for k in ["hours", "pricing", "quote", "estimate", "warranty", "guarantee"]):
        return "faq"
    if lower.strip() in {"hi", "hello", "hey"}:
        return "greeting"
    if lower.endswith("?"):
        return "faq"
    return "other"


async def classify_intent(text: str) -> str:
    """Classify user intent with heuristics and optional LLM fallback.

    Returns one of INTENT_LABELS and always falls back to deterministic
    heuristics for safety.
    """
    base = _heuristic_intent(text)
    settings = get_settings()
    speech = settings.speech
    if speech.provider != "openai" or not speech.openai_api_key:
        return base

    system_prompt = (
        "You classify caller utterances into intents for a plumbing booking assistant. "
        "Allowed intents: emergency, schedule, reschedule, cancel, faq, greeting, other. "
        "Return only the intent label."
    )
    payload = {
        "model": speech.openai_chat_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (text or "").strip()},
        ],
        "temperature": 0,
        "max_tokens": 4,
    }
    headers = {
        "Authorization": f"Bearer {speech.openai_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{speech.openai_api_base}/chat/completions"
    try:
        timeout = httpx.Timeout(6.0, connect=4.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "") or ""
            label = content.strip().split()[0].lower()
            if label in INTENT_LABELS:
                return label
    except Exception:
        logger.debug("intent_llm_fallback_failed", exc_info=True)
    return base
