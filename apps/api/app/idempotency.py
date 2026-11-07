"""Transaction-bound operation results. Keys never expire into unsafe re-execution."""

import hashlib
import json

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit import audit
from app.models import AuditEvent, OperationKey, User, WorkflowEvent
from app.operation_keys import resolve


def begin(db: Session, user: User, request: Request, payload: object) -> dict | None:
    # Signature, owner, epoch and expiry are checked before any lookup (see app.operation_keys).
    key, expires_at = resolve(request.headers.get("Idempotency-Key"), user)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"method": request.method, "path": request.url.path, "payload": jsonable_encoder(payload)},
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"operation:{user.id}:{key}"}
    )
    saved = db.scalar(select(OperationKey).where(OperationKey.actor_id == user.id, OperationKey.key == key))
    failed = failure(db, user.id, key)
    if failed and failed.safe_metadata.get("request_hash") != fingerprint:
        raise HTTPException(409, "idempotency_conflict")
    if db.scalar(
        select(WorkflowEvent.id)
        .where(WorkflowEvent.actor_id == user.id, WorkflowEvent.idempotency_key == key)
        .limit(1)
    ):
        raise HTTPException(409, "idempotency_conflict")
    if saved:
        if saved.fingerprint != fingerprint:
            raise HTTPException(409, "idempotency_conflict")
        return saved.response
    db.info["operation"] = (user.id, key, fingerprint, expires_at)
    return None


def finish(db: Session, response: dict) -> dict:
    operation = db.info.pop("operation", None)
    if operation:
        actor, key, fingerprint, expires_at = operation
        db.add(
            OperationKey(
                actor_id=actor, key=key, fingerprint=fingerprint, response=jsonable_encoder(response),
                expires_at=expires_at,
            )
        )
    db.commit()
    return response


def workflow_key(raw: str, user: User) -> str:
    """Validate a workflow body key and return the stored operation id."""
    return resolve(raw, user)[0]


def workflow_lock(db: Session, user: User, key: str) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"operation:{user.id}:{key}"}
    )
    if db.get(OperationKey, (user.id, key)) or failure(db, user.id, key):
        raise HTTPException(409, "idempotency_conflict")


def failure(db: Session, actor: str, key: str) -> AuditEvent | None:
    return db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.actor_id == actor,
            AuditEvent.action == "FILE_UPLOAD_BLOCKED",
            AuditEvent.safe_metadata["idempotency_key"].as_string() == key,
        )
        .limit(1)
    )


def upload_failed(db: Session, request: Request, user: User, document_id: str, reason: object) -> None:
    actor, key, fingerprint, _ = db.info.pop("operation")
    if failure(db, actor, key) is None:
        audit(
            db,
            request,
            user.id,
            "FILE_UPLOAD_BLOCKED",
            "document",
            document_id,
            {"reason": reason, "idempotency_key": key, "request_hash": fingerprint},
        )
    db.commit()
