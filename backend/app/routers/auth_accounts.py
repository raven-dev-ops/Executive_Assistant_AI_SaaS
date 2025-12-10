from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, EmailStr, Field

from ..db import SQLALCHEMY_AVAILABLE, SessionLocal
from ..db_models import BusinessDB, BusinessInviteDB, BusinessUserDB, UserDB
from ..config import get_settings
from ..deps import ensure_business_active
from ..metrics import metrics
from ..services.auth import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


router = APIRouter()


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str] = None
    active_business_id: Optional[str] = None
    roles: List[str] = []


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None
    role: str = "owner"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    business_id: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str
    business_id: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: UserResponse


class ResetInitRequest(BaseModel):
    email: EmailStr


class ResetInitResponse(BaseModel):
    message: str
    reset_token: Optional[str] = None


class ResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class ResetConfirmResponse(BaseModel):
    message: str


class InvitePreviewResponse(BaseModel):
    email: EmailStr
    role: str
    business_id: str
    business_name: str | None = None
    expires_at: datetime | None = None
    status: str


class InviteAcceptRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    name: Optional[str] = None


class MembershipResponse(BaseModel):
    business_id: str
    business_name: str | None = None
    role: str


class MyBusinessesResponse(BaseModel):
    memberships: list[MembershipResponse]


def _require_db():
    if not SQLALCHEMY_AVAILABLE or SessionLocal is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return SessionLocal()


def _ensure_business(business_id: str):
    session = _require_db()
    try:
        row = session.get(BusinessDB, business_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Business not found")
    finally:
        session.close()


def _validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _get_invite_by_token(session, token: str) -> BusinessInviteDB | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return (
        session.query(BusinessInviteDB)
        .filter(BusinessInviteDB.token_hash == token_hash)
        .one_or_none()
    )


def _get_memberships(session, user_id: str) -> list[BusinessUserDB]:
    return session.query(BusinessUserDB).filter(BusinessUserDB.user_id == user_id).all()


def _roles_for_business(
    business_id: str, memberships: list[BusinessUserDB]
) -> list[str]:
    roles = [m.role for m in memberships if m.business_id == business_id]
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not in business",
        )
    return roles


def _select_business_id(
    requested_business_id: str | None,
    user: UserDB,
    memberships: list[BusinessUserDB],
) -> str:
    if requested_business_id:
        return requested_business_id
    if user.active_business_id:
        return user.active_business_id
    if memberships:
        return memberships[0].business_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User has no business memberships",
    )


def _issue_tokens(
    user: UserDB,
    business_id: str,
    roles: list[str],
    settings,
) -> TokenResponse:
    access_token, access_expires_at = create_access_token(
        user_id=user.id,
        business_id=business_id,
        roles=roles,
        settings=settings,
    )
    refresh_token, refresh_expires_at = create_refresh_token(
        user_id=user.id,
        business_id=business_id,
        settings=settings,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        user=UserResponse(
            id=user.id,
            email=user.email,  # type: ignore[arg-type]
            name=user.name,
            active_business_id=business_id,
            roles=roles,
        ),
    )


def _resolve_user_from_auth(
    authorization: str | None,
    x_user_id: str | None,
) -> tuple[str, str | None]:
    settings = get_settings()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            decoded = decode_token(token, settings, expected_type="access")
        except TokenError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return decoded.user_id, decoded.business_id
    if x_user_id:
        return x_user_id, None
    raise HTTPException(status_code=401, detail="Missing authentication")


def _is_locked_out(user: UserDB) -> tuple[bool, int]:
    lockout_until = _normalize_dt(getattr(user, "lockout_until", None))
    if not lockout_until:
        return False, 0
    now = _now()
    if lockout_until and lockout_until > now:
        remaining = int((lockout_until - now).total_seconds())
        return True, max(remaining, 1)
    return False, 0


def _handle_login_failure(session, user: UserDB, settings) -> None:
    """Increment failure count and optionally lock the account."""
    user.failed_login_attempts = (getattr(user, "failed_login_attempts", 0) or 0) + 1
    limit = max(settings.auth.failed_attempt_limit, 1)
    if user.failed_login_attempts >= limit:
        lock_minutes = max(settings.auth.lockout_minutes, 1)
        user.lockout_until = _now() + timedelta(minutes=lock_minutes)
        user.failed_login_attempts = 0
    session.add(user)
    session.commit()
    session.refresh(user)


def _clear_lockout_state(user: UserDB) -> None:
    user.failed_login_attempts = 0
    user.lockout_until = None


def _upgrade_plaintext_password_if_needed(
    session, user: UserDB, provided_password: str
) -> bool:
    """If the stored password is plaintext and matches, rehash it."""
    stored = getattr(user, "password_hash", None)
    if stored and stored == provided_password:
        user.password_hash = hash_password(provided_password)
        session.add(user)
        session.commit()
        session.refresh(user)
        return True
    return False


@router.post("/register", response_model=UserResponse)
def register(
    payload: RegisterRequest,
    business_id: str = Depends(ensure_business_active),
) -> UserResponse:
    """Create a user, associate to business, and set active business."""
    allowed_roles = {"owner", "admin", "staff", "viewer"}
    if payload.role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role")
    _validate_password_strength(payload.password)
    session = _require_db()
    try:
        existing = (
            session.query(UserDB)
            .filter(UserDB.email == str(payload.email))
            .one_or_none()
        )
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        user_id = secrets.token_hex(8)
        user = UserDB(
            id=user_id,
            email=str(payload.email),
            password_hash=hash_password(payload.password),
            name=payload.name,
            active_business_id=business_id,
        )  # type: ignore[call-arg]
        session.add(user)

        bu = BusinessUserDB(
            id=secrets.token_hex(8),
            business_id=business_id,
            user_id=user_id,
            role=payload.role,
        )  # type: ignore[call-arg]
        session.add(bu)
        session.commit()
        session.refresh(user)
        metrics.users_registered += 1
        return UserResponse(
            id=user.id,
            email=user.email,  # type: ignore[arg-type]
            name=user.name,
            active_business_id=user.active_business_id,
            roles=[payload.role],
        )
    finally:
        session.close()


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
) -> TokenResponse:
    """Authenticate a user and issue access/refresh tokens."""
    session = _require_db()
    settings = get_settings()
    try:
        user = (
            session.query(UserDB)
            .filter(UserDB.email == str(payload.email))
            .one_or_none()
        )
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        locked, retry_after = _is_locked_out(user)
        if locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account locked due to repeated failures. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        if verify_password(payload.password, user.password_hash):
            verified = True
        else:
            verified = _upgrade_plaintext_password_if_needed(
                session, user, payload.password
            )

        if not verified:
            _handle_login_failure(session, user, settings)
            locked, retry_after = _is_locked_out(user)
            if locked:
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account locked due to repeated failures. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        memberships = _get_memberships(session, user.id)
        business_id = _select_business_id(payload.business_id, user, memberships)
        roles = _roles_for_business(business_id, memberships)
        _clear_lockout_state(user)
        user.active_business_id = business_id
        session.add(user)
        session.commit()
        session.refresh(user)
        return _issue_tokens(user, business_id, roles, settings)
    finally:
        session.close()


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest) -> TokenResponse:
    """Exchange a refresh token for a new access/refresh pair."""
    settings = get_settings()
    session = _require_db()
    try:
        try:
            decoded = decode_token(
                payload.refresh_token, settings, expected_type="refresh"
            )
        except TokenError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user = session.get(UserDB, decoded.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        memberships = _get_memberships(session, user.id)
        business_id = _select_business_id(
            payload.business_id or decoded.business_id, user, memberships
        )
        roles = _roles_for_business(business_id, memberships)
        user.active_business_id = business_id
        session.add(user)
        session.commit()
        session.refresh(user)
        return _issue_tokens(user, business_id, roles, settings)
    finally:
        session.close()


@router.post("/reset/init", response_model=ResetInitResponse)
def reset_init(payload: ResetInitRequest) -> ResetInitResponse:
    """Begin a password reset by issuing a time-bound reset token."""
    settings = get_settings()
    session = _require_db()
    try:
        user = (
            session.query(UserDB)
            .filter(UserDB.email == str(payload.email))
            .one_or_none()
        )
        message = "If that account exists, a reset link has been generated."
        if not user:
            return ResetInitResponse(message=message)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = _now() + timedelta(
            minutes=settings.auth.reset_token_expires_minutes
        )
        user.reset_token_hash = token_hash
        user.reset_token_expires_at = expires_at
        session.add(user)
        session.commit()
        session.refresh(user)
        testing_mode = os.getenv("TESTING", "false").lower() == "true" or bool(
            os.getenv("PYTEST_CURRENT_TEST")
        )
        reset_token = token if testing_mode else None
        return ResetInitResponse(message=message, reset_token=reset_token)
    finally:
        session.close()


@router.post("/reset/confirm", response_model=ResetConfirmResponse)
def reset_confirm(payload: ResetConfirmRequest) -> ResetConfirmResponse:
    """Complete a password reset using the provided reset token."""
    _validate_password_strength(payload.new_password)
    session = _require_db()
    try:
        token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
        user = (
            session.query(UserDB)
            .filter(UserDB.reset_token_hash == token_hash)
            .one_or_none()
        )
        if not user or not getattr(user, "reset_token_expires_at", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )
        expires_at = _normalize_dt(user.reset_token_expires_at)
        if not expires_at or expires_at < _now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )
        user.password_hash = hash_password(payload.new_password)
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        _clear_lockout_state(user)
        session.add(user)
        session.commit()
        session.refresh(user)
        return ResetConfirmResponse(
            message="Password has been reset. You can now log in."
        )
    finally:
        session.close()


@router.get("/invite/preview", response_model=InvitePreviewResponse)
def invite_preview(token: str) -> InvitePreviewResponse:
    """Preview an invite token to show who/where it will join."""
    session = _require_db()
    try:
        invite = _get_invite_by_token(session, token)
        if not invite:
            raise HTTPException(status_code=400, detail="Invalid invite token")
        expires_at = _normalize_dt(getattr(invite, "expires_at", None))
        status = "pending"
        now = _now()
        if getattr(invite, "accepted_at", None):
            status = "accepted"
        elif expires_at and expires_at < now:
            status = "expired"
        business = session.get(BusinessDB, invite.business_id)
        return InvitePreviewResponse(
            email=invite.email,  # type: ignore[arg-type]
            role=invite.role,
            business_id=invite.business_id,
            business_name=business.name if business else None,  # type: ignore[union-attr]
            expires_at=expires_at,
            status=status,
        )
    finally:
        session.close()


@router.post("/invite/accept", response_model=TokenResponse)
def invite_accept(payload: InviteAcceptRequest) -> TokenResponse:
    """Accept an invite token, create the user if needed, and issue tokens."""
    _validate_password_strength(payload.password)
    settings = get_settings()
    session = _require_db()
    try:
        invite = _get_invite_by_token(session, payload.token)
        if not invite:
            raise HTTPException(status_code=400, detail="Invalid invite token")
        now = _now()
        expires_at = _normalize_dt(getattr(invite, "expires_at", None))
        if getattr(invite, "accepted_at", None):
            raise HTTPException(status_code=400, detail="Invite already used")
        if expires_at and expires_at < now:
            raise HTTPException(status_code=400, detail="Invite expired")

        business = session.get(BusinessDB, invite.business_id)
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        user = session.query(UserDB).filter(UserDB.email == invite.email).one_or_none()
        if user:
            user.password_hash = hash_password(payload.password)
            if payload.name:
                user.name = payload.name
        else:
            user = UserDB(
                id=secrets.token_hex(8),
                email=invite.email,
                password_hash=hash_password(payload.password),
                name=payload.name,
                active_business_id=invite.business_id,
            )  # type: ignore[call-arg]
            session.add(user)

        # Link the user to the business with the invited role.
        membership = (
            session.query(BusinessUserDB)
            .filter(
                BusinessUserDB.user_id == user.id,
                BusinessUserDB.business_id == invite.business_id,
            )
            .one_or_none()
        )
        if membership:
            membership.role = invite.role
        else:
            membership = BusinessUserDB(
                id=secrets.token_hex(8),
                business_id=invite.business_id,
                user_id=user.id,
                role=invite.role,
            )  # type: ignore[call-arg]
            session.add(membership)

        # Mark invite as accepted and set active business for the user.
        invite.accepted_at = now
        invite.accepted_by_user_id = user.id
        user.active_business_id = invite.business_id
        session.add(user)
        session.add(invite)
        session.commit()
        session.refresh(user)
        memberships = _get_memberships(session, user.id)
        roles = _roles_for_business(invite.business_id, memberships)
        return _issue_tokens(user, invite.business_id, roles, settings)
    finally:
        session.close()


@router.get("/me", response_model=UserResponse)
def me(
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    business_id: str = Depends(ensure_business_active),
) -> UserResponse:
    """Return the current user and active business context."""
    user_id, token_business_id = _resolve_user_from_auth(authorization, x_user_id)
    if token_business_id and token_business_id != business_id:
        raise HTTPException(status_code=403, detail="Business mismatch")
    session = _require_db()
    try:
        user = session.get(UserDB, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        memberships = _get_memberships(session, user.id)
        roles = _roles_for_business(business_id, memberships)
        return UserResponse(
            id=user.id,
            email=user.email,  # type: ignore[arg-type]
            name=user.name,
            active_business_id=user.active_business_id,
            roles=roles,
        )
    finally:
        session.close()


@router.get("/me/businesses", response_model=MyBusinessesResponse)
def my_businesses(
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> MyBusinessesResponse:
    """List the businesses and roles for the current user."""
    user_id, _ = _resolve_user_from_auth(authorization, x_user_id)
    session = _require_db()
    try:
        user = session.get(UserDB, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        memberships = _get_memberships(session, user_id)
        memberships_resp: list[MembershipResponse] = []
        for m in memberships:
            business = session.get(BusinessDB, m.business_id)
            memberships_resp.append(
                MembershipResponse(
                    business_id=m.business_id,
                    business_name=business.name if business else None,  # type: ignore[union-attr]
                    role=getattr(m, "role", "viewer"),
                )
            )
        return MyBusinessesResponse(memberships=memberships_resp)
    finally:
        session.close()


class ActiveBusinessRequest(BaseModel):
    business_id: str


@router.patch("/active-business", response_model=UserResponse)
def set_active_business(
    payload: ActiveBusinessRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UserResponse:
    """Update the active business for the current user."""
    user_id, _ = _resolve_user_from_auth(authorization, x_user_id)
    _ensure_business(payload.business_id)
    session = _require_db()
    try:
        user = session.get(UserDB, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        memberships = _get_memberships(session, user.id)
        _roles_for_business(payload.business_id, memberships)
        user.active_business_id = payload.business_id
        session.add(user)
        session.commit()
        session.refresh(user)
        roles = [m.role for m in memberships if m.business_id == payload.business_id]
        return UserResponse(
            id=user.id,
            email=user.email,  # type: ignore[arg-type]
            name=user.name,
            active_business_id=user.active_business_id,
            roles=roles,
        )
    finally:
        session.close()
