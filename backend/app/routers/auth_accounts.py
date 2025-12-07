from __future__ import annotations

import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr

from ..db import SQLALCHEMY_AVAILABLE, SessionLocal
from ..db_models import BusinessDB, BusinessUserDB, UserDB
from ..deps import ensure_business_active
from ..metrics import metrics


router = APIRouter()


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str] = None
    active_business_id: Optional[str] = None
    roles: List[str] = []


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


@router.post("/register", response_model=UserResponse)
def register(
    email: EmailStr,
    password: str,
    name: Optional[str] = None,
    business_id: str = Depends(ensure_business_active),
) -> UserResponse:
    """Create a user, associate to business, and set active business."""
    session = _require_db()
    try:
        existing = (
            session.query(UserDB).filter(UserDB.email == str(email)).one_or_none()
        )
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        user_id = secrets.token_hex(8)
        user = UserDB(
            id=user_id,
            email=str(email),
            password_hash=password,
            name=name,
            active_business_id=business_id,
        )  # type: ignore[call-arg]
        session.add(user)

        bu = BusinessUserDB(
            id=secrets.token_hex(8),
            business_id=business_id,
            user_id=user_id,
            role="owner",
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
            roles=["owner"],
        )
    finally:
        session.close()


@router.get("/me", response_model=UserResponse)
def me(
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    business_id: str = Depends(ensure_business_active),
) -> UserResponse:
    """Return the current user and active business context."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID")
    session = _require_db()
    try:
        user = session.get(UserDB, x_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        memberships = (
            session.query(BusinessUserDB)
            .filter(BusinessUserDB.user_id == x_user_id)
            .all()
        )
        roles = [m.role for m in memberships if m.business_id == business_id]
        if not roles:
            raise HTTPException(status_code=403, detail="User not in business")
        return UserResponse(
            id=user.id,
            email=user.email,  # type: ignore[arg-type]
            name=user.name,
            active_business_id=user.active_business_id,
            roles=roles,
        )
    finally:
        session.close()


class ActiveBusinessRequest(BaseModel):
    business_id: str


@router.patch("/active-business", response_model=UserResponse)
def set_active_business(
    payload: ActiveBusinessRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> UserResponse:
    """Update the active business for the current user."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID")
    _ensure_business(payload.business_id)
    session = _require_db()
    try:
        user = session.get(UserDB, x_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.active_business_id = payload.business_id
        session.add(user)
        session.commit()
        session.refresh(user)
        memberships = (
            session.query(BusinessUserDB)
            .filter(BusinessUserDB.user_id == x_user_id)
            .all()
        )
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
