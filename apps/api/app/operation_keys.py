"""Server-issued, signed, expiring retry keys (pre-deployment blocker B2).

The client obtains a key BEFORE sending a mutation and reuses it for retries. The token
carries the actor, a random operation id, issue/expiry times and the key epoch, signed with
HMAC-SHA256. Validation happens before any lookup, so an expired key is always rejected
with 409 operation_expired even after its stored result has been purged: a purged
operation can never execute a second time. Storage keeps only the inner operation id
(a UUID), so existing key columns, workflow history and audit stay unchanged.

Legacy client UUID keys are accepted until LEGACY_OPERATION_KEYS_UNTIL (unset = accepted,
development only). Raising OPERATION_KEY_EPOCH invalidates every outstanding token, for
example after restoring an older backup.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.auth import Actor
from app.config import settings
from app.models import User

PREFIX = "nx1"
MAX_CLOCK_SKEW = timedelta(minutes=5)
router = APIRouter(prefix="/operation-keys", tags=["operation-keys"])


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(settings().operation_key_secret.encode(), payload.encode(), hashlib.sha256).digest())


def issue(user: User, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or datetime.now(UTC)
    expires = now + timedelta(days=settings().operation_key_ttl_days)
    claims = {"a": user.id, "k": str(uuid.uuid4()), "i": int(now.timestamp()), "x": int(expires.timestamp()),
              "e": settings().operation_key_epoch}
    payload = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    return f"{PREFIX}.{payload}.{_sign(payload)}", expires


def resolve(raw: str | None, user: User, now: datetime | None = None) -> tuple[str, datetime | None]:
    """Validate a supplied key; return (stored operation id, expiry or None for legacy keys)."""
    if raw is None:
        raise HTTPException(422, "idempotency_key_required")
    now = now or datetime.now(UTC)
    if not raw.startswith(PREFIX + "."):
        try:
            key = str(uuid.UUID(raw))
        except ValueError:
            raise HTTPException(422, "invalid_idempotency_key") from None
        until = settings().legacy_operation_keys_until
        if until is not None and now >= until:
            raise HTTPException(409, "operation_legacy_rejected")
        return key, None
    try:
        _, payload, signature = raw.split(".")
        if not hmac.compare_digest(signature, _sign(payload)):
            raise ValueError("signature")
        claims = json.loads(_unb64(payload))
        key, issued, expires = str(uuid.UUID(claims["k"])), int(claims["i"]), int(claims["x"])
        actor, epoch = claims["a"], int(claims["e"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "invalid_idempotency_key") from None
    if not hmac.compare_digest(str(actor), user.id):
        raise HTTPException(422, "invalid_idempotency_key")
    if issued > (now + MAX_CLOCK_SKEW).timestamp():
        raise HTTPException(422, "invalid_idempotency_key")
    # Expired or from another epoch: never execute, never silently swap in a new key.
    if epoch != settings().operation_key_epoch or now.timestamp() >= expires:
        raise HTTPException(409, "operation_expired")
    return key, datetime.fromtimestamp(expires, UTC)


@router.post("", status_code=201)
def create_operation_key(user: Actor) -> dict:
    # Stateless: issuing stores nothing, so it cannot grow the database.
    token, expires = issue(user)
    return {"key": token, "expires_at": expires}
