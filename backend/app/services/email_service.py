from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import httpx

from ..config import get_settings
from ..services.oauth_tokens import oauth_store


logger = logging.getLogger(__name__)


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str
    business_id: str | None = None
    provider: str = "stub"


@dataclass
class EmailResult:
    sent: bool
    detail: str | None = None
    provider: str = "stub"


class EmailService:
    """Lightweight Gmail-based email sender with stub fallback.

    Uses per-tenant OAuth tokens stored in oauth_store under provider "gmail".
    When Gmail is not configured, messages are recorded locally for testing and
    stubbed as unsent.
    """

    def __init__(self) -> None:
        self._sent: List[SentEmail] = []

    @property
    def sent_messages(self) -> List[SentEmail]:
        return list(self._sent)

    def _encode_message(self, from_email: str, to: str, subject: str, body: str) -> str:
        raw = (
            f"From: {from_email}\r\n"
            f"To: {to}\r\n"
            f"Subject: {subject}\r\n"
            'Content-Type: text/plain; charset="utf-8"\r\n'
            "\r\n"
            f"{body}"
        ).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8")

    async def _refresh_token_if_needed(
        self, business_id: str, client_id: str | None, client_secret: str | None
    ):
        tok = oauth_store.get_tokens("gmail", business_id)
        if not tok:
            return None
        now = time.time()
        if tok.expires_at - now > 60:
            return tok
        # Try real refresh if credentials are available; otherwise fall back to stub refresh.
        if client_id and client_secret and tok.refresh_token:
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": tok.refresh_token,
                "grant_type": "refresh_token",
            }
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(token_url, data=data)
                if resp.status_code == 200:
                    payload = resp.json()
                    access_token = payload.get("access_token")
                    expires_in = int(payload.get("expires_in") or 3600)
                    if access_token:
                        return oauth_store.save_tokens(
                            "gmail",
                            business_id,
                            access_token=access_token,
                            refresh_token=tok.refresh_token,
                            expires_in=expires_in,
                        )
            except Exception:
                logger.warning(
                    "email_refresh_failed", exc_info=True, extra={"business_id": business_id}
                )
        # Stub refresh path.
        return oauth_store.refresh("gmail", business_id)

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        business_id: str | None = None,
        from_email: str | None = None,
    ) -> EmailResult:
        settings = get_settings()
        gmail_cfg = settings.oauth
        provider = "gmail"
        # Always record locally for observability.
        self._sent.append(
            SentEmail(
                to=to,
                subject=subject,
                body=body,
                business_id=business_id,
                provider=provider,
            )
        )

        if not business_id:
            return EmailResult(sent=False, detail="Missing business_id", provider="stub")

        # Pull tokens and refresh if close to expiry.
        try:
            tok = await self._refresh_token_if_needed(
                business_id, gmail_cfg.google_client_id, gmail_cfg.google_client_secret
            )
        except KeyError:
            tok = None
        if not tok:
            return EmailResult(
                sent=False, detail="Gmail tokens not found for tenant", provider="stub"
            )

        if not from_email:
            # When not provided, attempt to use the Gmail account; otherwise stub.
            from_email = "me"

        raw = self._encode_message(from_email, to, subject, body)
        headers = {"Authorization": f"Bearer {tok.access_token}"}
        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json={"raw": raw})
            if resp.status_code >= 200 and resp.status_code < 300:
                return EmailResult(sent=True, detail=None, provider="gmail")
            logger.warning(
                "email_send_failed",
                extra={"business_id": business_id, "status": resp.status_code, "body": resp.text},
            )
            return EmailResult(
                sent=False,
                detail=f"Gmail send failed ({resp.status_code})",
                provider="gmail",
            )
        except Exception:
            logger.exception(
                "email_send_exception", extra={"business_id": business_id, "provider": "gmail"}
            )
            return EmailResult(sent=False, detail="Exception during send", provider="gmail")

    async def notify_owner(
        self,
        subject: str,
        body: str,
        *,
        business_id: str,
        owner_email: str | None = None,
    ) -> EmailResult:
        to = owner_email
        if not to and business_id and get_settings().sms.owner_number:
            # No email configured; signal unsent.
            return EmailResult(sent=False, detail="Owner email not configured", provider="stub")
        return await self.send_email(
            to=to or "",
            subject=subject,
            body=body,
            business_id=business_id,
            from_email=to or None,
        )


email_service = EmailService()
