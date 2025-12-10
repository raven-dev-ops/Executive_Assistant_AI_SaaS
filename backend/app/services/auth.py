from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import List

import bcrypt
import jwt

from ..config import AppSettings


class TokenError(Exception):
    """Raised when a JWT cannot be verified."""


@dataclass
class DecodedToken:
    user_id: str
    business_id: str | None
    roles: list[str]
    token_type: str
    expires_at: datetime


def hash_password(password: str) -> str:
    """Return a bcrypt hash for the supplied password."""
    pw_bytes = password.encode("utf-8")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str | None) -> bool:
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def _build_payload(
    user_id: str,
    business_id: str | None,
    roles: List[str],
    token_type: str,
    ttl_minutes: int,
) -> dict:
    issued_at = _now()
    expires_at = issued_at + timedelta(minutes=ttl_minutes)
    return {
        "sub": user_id,
        "biz": business_id,
        "roles": roles,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": token_type,
    }


def create_access_token(
    user_id: str,
    business_id: str | None,
    roles: List[str],
    settings: AppSettings,
) -> tuple[str, datetime]:
    payload = _build_payload(
        user_id,
        business_id,
        roles,
        "access",
        settings.auth.access_token_expires_minutes,
    )
    token = jwt.encode(payload, settings.auth.secret, algorithm=settings.auth.algorithm)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    return token, expires_at


def create_refresh_token(
    user_id: str,
    business_id: str | None,
    settings: AppSettings,
) -> tuple[str, datetime]:
    payload = _build_payload(
        user_id,
        business_id,
        [],
        "refresh",
        settings.auth.refresh_token_expires_minutes,
    )
    token = jwt.encode(payload, settings.auth.secret, algorithm=settings.auth.algorithm)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    return token, expires_at


def decode_token(
    token: str,
    settings: AppSettings,
    expected_type: str = "access",
) -> DecodedToken:
    try:
        payload = jwt.decode(
            token,
            settings.auth.secret,
            algorithms=[settings.auth.algorithm],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:  # type: ignore[attr-defined]
        raise TokenError("token_expired") from exc
    except Exception as exc:
        raise TokenError("token_invalid") from exc

    token_type = payload.get("typ")
    if expected_type and token_type != expected_type:
        raise TokenError("unexpected_token_type")

    user_id = payload.get("sub")
    if not user_id:
        raise TokenError("missing_subject")

    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
    return DecodedToken(
        user_id=str(user_id),
        business_id=payload.get("biz"),
        roles=list(payload.get("roles", [])) if token_type == "access" else [],
        token_type=token_type or "unknown",
        expires_at=expires_at,
    )
