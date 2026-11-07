import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.client_ip import client_address
from app.config import settings
from app.db import get_db
from app.models import AuthSession, LoginThrottle, User
from app.policy import require
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
        "updated_at": user.updated_at.isoformat(),
    }


@router.post("/login", response_model=SessionOut)
def login(body: Login, request: Request, response: Response, db: Db) -> dict:
    now = datetime.now(UTC)
    # Per-account and per-client limits. X-Forwarded-For is honoured only from TRUSTED_PROXIES;
    # an undeterminable client gets no shared bucket, so one attacker cannot lock out everyone.
    keys = [digest("account:" + body.email.lower())]
    client = client_address(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        settings().trusted_proxies,
    )
    if client:
        keys.append(digest("peer:" + client))
    buckets = []
    for key in sorted(keys):
        bucket = None
        # The operator purge (app.auth_cleanup) may delete a stale row between insert and lock.
        for _ in range(3):
            db.execute(
                insert(LoginThrottle).values(id=key, failures=0, window_start=now).on_conflict_do_nothing()
            )
            bucket = db.scalar(select(LoginThrottle).where(LoginThrottle.id == key).with_for_update())
            if bucket is not None:
                break
        if bucket is None:
            raise HTTPException(503, "login_temporarily_unavailable")
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
            user_agent="".join(c for c in request.headers.get("user-agent", "") if c.isprintable())[:200],
            user_id=user.id,
            csrf_token=csrf,
            expires_at=now + timedelta(hours=settings().session_hours),
        )
    )
    db.flush()
    excess = list(
        db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.expires_at > now)
            .order_by(AuthSession.created_at.desc(), AuthSession.id)
            .offset(20)
        )
    )
    for expired in excess:
        db.delete(expired)
    if excess:
        audit(db, request, user.id, "SESSIONS_PRUNED", "user", user.id, {"count": len(excess)})
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


@router.get("/sessions")
def sessions(request: Request, db: Db, user: Actor) -> list[dict]:
    current = request.state.auth_session.id
    return [
        {
            "id": s.public_id,
            "user_agent": s.user_agent,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "current": s.id == current,
        }
        for s in db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.expires_at > datetime.now(UTC))
            .order_by(AuthSession.created_at.desc())
            .limit(20)
        )
    ]


@router.post("/sessions/revoke-others", status_code=204)
def revoke_others(request: Request, db: Db, user: Actor):
    deleted = db.scalars(
        delete(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.id != request.state.auth_session.id)
        .returning(AuthSession.public_id)
    ).all()
    audit(db, request, user.id, "SESSIONS_REVOKED", "user", user.id, {"count": len(deleted)})
    db.commit()


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, request: Request, response: Response, db: Db, user: Actor):
    row = db.scalar(
        select(AuthSession)
        .where(AuthSession.public_id == session_id, AuthSession.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "not_found")
    current = row.id == request.state.auth_session.id
    db.delete(row)
    audit(db, request, user.id, "SESSION_REVOKED", "user", user.id, {"current": current})
    db.commit()
    if current:
        response.delete_cookie("nexora_session", path="/")


@router.post("/users/{user_id}/sessions/revoke", status_code=204)
def admin_revoke_sessions(user_id: str, request: Request, response: Response, db: Db, user: Actor):
    require(user, "admin")
    if db.get(User, user_id) is None:
        raise HTTPException(404, "not_found")
    deleted = db.scalars(
        delete(AuthSession).where(AuthSession.user_id == user_id).returning(AuthSession.public_id)
    ).all()
    audit(db, request, user.id, "SESSIONS_REVOKED", "user", user_id, {"count": len(deleted)})
    db.commit()
    if user_id == user.id:
        response.delete_cookie("nexora_session", path="/")
