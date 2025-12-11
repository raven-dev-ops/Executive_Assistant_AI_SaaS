from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from ..config import get_settings
from ..metrics import metrics


@dataclass
class OwnerAssistantAnswer:
    answer: str
    used_model: Optional[str] = None


class OwnerAssistantService:
    """Lightweight owner-facing assistant backed by OpenAI when configured.

    This service is intentionally narrow in scope. It is designed to answer
    questions about:
    - the owner dashboard and its metrics/cards
    - the underlying system and data model
    - privacy, security, and operational policies

    When SPEECH_PROVIDER is not set to "openai" or OPENAI_API_KEY is not
    configured, the assistant returns a static guidance message instead of
    attempting external calls.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._speech = settings.speech
        self._docs_cache: Optional[str] = None

    def _load_reference_docs(self) -> str:
        """Best-effort load of local markdown docs for grounding.

        The content is truncated to keep prompts lightweight. Failures are
        swallowed so a missing file never breaks the assistant.
        """
        if self._docs_cache is not None:
            return self._docs_cache

        try:
            root = Path(__file__).resolve().parents[2]
        except Exception:
            self._docs_cache = ""
            return self._docs_cache

        candidates = [
            ("README", root / "README.md"),
            ("DASHBOARD", root / "dashboard" / "DASHBOARD.md"),
            ("API_REFERENCE", root / "API_REFERENCE.md"),
            ("DATA_MODEL", root / "DATA_MODEL.md"),
            ("RUNBOOK", root / "RUNBOOK.md"),
            ("SECURITY", root / "SECURITY.md"),
            ("PRIVACY_POLICY", root / "PRIVACY_POLICY.md"),
        ]

        parts: list[str] = []
        for label, path in candidates:
            try:
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                # Skip unreadable files but continue aggregating others.
                continue
            # Keep each document reasonably small in the prompt.
            if len(text) > 4000:
                text = text[:4000]
            parts.append(f"## {label}\n{text}")

        self._docs_cache = "\n\n".join(parts)
        return self._docs_cache

    async def answer(
        self,
        question: str,
        business_context: Optional[str] = None,
        business_id: str | None = None,
    ) -> OwnerAssistantAnswer:
        """Return an answer for the owner's question.

        Uses OpenAI chat completions when configured, otherwise falls back
        to a static, helpful message.
        """
        question = (question or "").strip()
        if not question:
            return OwnerAssistantAnswer(
                answer=(
                    "Please type a question about your dashboard, metrics, "
                    "data, policies, or operations and I'll do my best to help."
                ),
            )

        metrics_context = self._summarize_metrics(business_id)

        # Only attempt real LLM calls when configured for OpenAI.
        if self._speech.provider != "openai" or not self._speech.openai_api_key:
            if metrics_context:
                return OwnerAssistantAnswer(
                    answer=(
                        "The AI owner assistant is not fully configured yet.\n\n"
                        f"Recent metrics for this tenant:\n{metrics_context}\n\n"
                        "To enable rich answers, set SPEECH_PROVIDER=openai and provide "
                        "a valid OPENAI_API_KEY (and optionally OPENAI_CHAT_MODEL)."
                    ),
                )
            return OwnerAssistantAnswer(
                answer=(
                    "The AI owner assistant is not fully configured yet.\n\n"
                    "- To enable rich answers, set SPEECH_PROVIDER=openai and provide\n"
                    "  a valid OPENAI_API_KEY (and optionally OPENAI_CHAT_MODEL).\n"
                    "- In the meantime, you can refer to the in-repo docs such as "
                    "DASHBOARD.md, DATA_MODEL.md, SECURITY.md, and RUNBOOK.md."
                ),
            )

        docs = self._load_reference_docs()
        system_instructions = (
            "You are the Owner Assistant for an AI telephony + CRM platform "
            "used by service-business owners.\n"
            "- Answer questions about the owner dashboard, its cards and KPIs.\n"
            "- Explain metrics, data fields, and how they are calculated.\n"
            "- Summarize privacy, security, and operational policies based on "
            "the reference docs.\n"
            "- When you are unsure, say you are unsure and suggest where in the "
            "docs the owner can look.\n"
            "- Be concise and use plain language.\n"
        )

        messages = [
            {
                "role": "system",
                "content": system_instructions,
            },
        ]
        if metrics_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Latest tenant metrics:\n{metrics_context}",
                }
            )
        if business_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Business context for this tenant:\n{business_context}",
                }
            )
        if docs:
            messages.append(
                {
                    "role": "system",
                    "content": f"Reference documentation:\n{docs}",
                }
            )
        messages.append(
            {
                "role": "user",
                "content": question,
            }
        )

        url = f"{self._speech.openai_api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._speech.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._speech.openai_chat_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 512,
        }

        try:
            timeout = httpx.Timeout(20.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            # Fall back gracefully if the LLM call fails for any reason.
            return OwnerAssistantAnswer(
                answer=(
                    "I wasn't able to reach the AI assistant service right now. "
                    "Please try again in a moment, or refer to the local docs "
                    "such as DASHBOARD.md, DATA_MODEL.md, SECURITY.md, and RUNBOOK.md."
                ),
            )

        try:
            choice = data.get("choices", [])[0]
            message = choice.get("message", {})
            content = message.get("content") or ""
        except Exception:
            content = ""

        if not content:
            content = (
                "I couldn't generate a detailed answer for that question. "
                "Please try rephrasing, or consult the owner documentation."
            )

        used_model = data.get("model") or self._speech.openai_chat_model
        return OwnerAssistantAnswer(answer=content, used_model=used_model)

    def _summarize_metrics(self, business_id: str | None) -> str:
        """Return a compact, human-readable metrics snapshot for a tenant."""
        if not business_id:
            return ""
        twilio = metrics.twilio_by_business.get(business_id)
        sms = metrics.sms_by_business.get(business_id)
        callbacks = metrics.callbacks_by_business.get(business_id, {})
        voice_sessions = metrics.voice_sessions_by_business.get(business_id)
        parts: list[str] = []
        if twilio:
            parts.append(
                f"Voice requests: {twilio.voice_requests}, voice errors: {twilio.voice_errors}"
            )
            parts.append(
                f"SMS requests: {twilio.sms_requests}, sms errors: {twilio.sms_errors}"
            )
        if sms:
            parts.append(
                f"SMS sent (owner/customer): {sms.sms_sent_owner}/{sms.sms_sent_customer}, opt-outs: {sms.sms_opt_out_events}"
            )
            parts.append(
                f"Retention SMS sent: {sms.retention_messages_sent}, followups: {sms.lead_followups_sent}"
            )
        if callbacks:
            parts.append(f"Pending callbacks/voicemails: {len(callbacks)}")
        if voice_sessions:
            parts.append(
                f"Voice sessions (requests/errors): {voice_sessions.requests}/{voice_sessions.errors}"
            )
        return "\n".join(parts)


owner_assistant_service = OwnerAssistantService()
