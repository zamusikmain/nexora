import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.db import get_db
from app.models import AuthSession, LoginThrottle, User
from app.schemas import Login, SessionOut

router = APIRouter(prefix="/auth", tags=["auth"])
password_hasher = PasswordHasher()
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
Db = Annotated[Session, Depends(get_db)]


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request, db: Db) -> User:
    token = request.cookies.get("nexora_session", "")
    session = db.get(AuthSession, digest(token)) if token else None
    if not session or session.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "unauthorized")
    user = db.get(User, session.user_id)
    if not user or user.status != "ACTIVE":
        raise HTTPException(401, "unauthorized")
    request.state.auth_session = session
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(403, "csrf_failed")
    return user


Actor = Annotated[User, Depends(current_user)]


def public_user(user: User) -> dict[str, str | None]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "status": user.status,
        "department_id": user.department_id,
    }


@router.post("/login", response_model=SessionOut)
def login(body: Login, request: Request, response: Response, db: Db) -> dict:
    now = datetime.now(UTC)
    # Per-account and per-direct-peer limits. Never trust forwarded client IP headers.
    keys = [
        digest("account:" + body.email.lower()),
        digest("peer:" + (request.client.host if request.client else "unknown")),
    ]
    buckets = []
    for key in sorted(keys):
        db.execute(
            insert(LoginThrottle).values(id=key, failures=0, window_start=now).on_conflict_do_nothing()
        )
        bucket = db.scalar(select(LoginThrottle).where(LoginThrottle.id == key).with_for_update())
        assert bucket is not None
        if bucket.window_start + timedelta(minutes=15) <= now:
            bucket.window_start, bucket.failures = now, 0
        buckets.append(bucket)
    if any(bucket.failures >= 20 for bucket in buckets):
        db.commit()
        raise HTTPException(429, "login_rate_limited")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid: bool
    try:
        valid = password_hasher.verify(user.password_hash if user else _dummy_hash, body.password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or not user or user.status != "ACTIVE":
        for bucket in buckets:
            bucket.failures += 1
        audit(db, request, None, "USER_LOGIN_FAILED", "user", None)
        db.commit()
        raise HTTPException(401, "invalid_credentials")
    old_token = request.cookies.get("nexora_session")
    if old_token:
        old = db.get(AuthSession, digest(old_token))
        if old:
            db.delete(old)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            id=digest(token),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=now + timedelta(hours=settings().session_hours),
        )
    )
    audit(db, request, user.id, "USER_LOGIN", "user", user.id)
    db.commit()
    response.set_cookie(
        "nexora_session",
        token,
        httponly=True,
        samesite="lax",
        secure=settings().app_env != "development",
        path="/",
        max_age=settings().session_hours * 3600,
    )
    return {"user": public_user(user), "csrf_token": csrf}


@router.get("/me", response_model=SessionOut)
def me(request: Request, user: Actor) -> dict:
    return {"user": public_user(user), "csrf_token": request.state.auth_session.csrf_token}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: Actor, db: Db) -> None:
    db.delete(request.state.auth_session)
    audit(db, request, user.id, "USER_LOGOUT", "user", user.id)
    db.commit()
    response.delete_cookie("nexora_session", path="/")
