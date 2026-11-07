"""Operator purge of expired signed operation keys (B2). Dry-run by default.

Run with the migrations/owner connection (DATABASE_URL); the runtime role has no DELETE on
operation_keys. Safe because app.operation_keys rejects an expired key with 409
operation_expired before any lookup, so a purged operation can never execute again. The
database trigger additionally refuses legacy rows and keys expired less than a day ago.
"""

import argparse
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, tuple_

from app.db import SessionLocal
from app.models import AuditEvent, OperationKey

BATCH = 1000


def purge(*, apply: bool = False, grace_hours: int = 48, now: datetime | None = None) -> dict:
    if grace_hours < 24:
        raise ValueError("At least 24 hours grace is required")
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=grace_hours)
    expired = OperationKey.expires_at.is_not(None) & (OperationKey.expires_at < cutoff)
    with SessionLocal() as db:
        planned = db.scalar(select(func.count()).select_from(OperationKey).where(expired)) or 0
        legacy = db.scalar(select(func.count()).select_from(OperationKey).where(OperationKey.expires_at.is_(None)))
        if not apply:
            return {"dry_run": True, "planned": planned, "deleted": None, "legacy_kept": legacy,
                    "grace_hours": grace_hours}
        deleted = 0
        while True:
            batch = select(OperationKey.actor_id, OperationKey.key).where(expired).limit(BATCH).with_for_update(
                skip_locked=True)
            removed = len(db.execute(delete(OperationKey).where(
                tuple_(OperationKey.actor_id, OperationKey.key).in_(batch), expired,
            ).returning(OperationKey.key)).all())
            db.commit()
            deleted += removed
            if removed < BATCH:
                break
        db.add(AuditEvent(actor_id=None, action="OPERATION_KEYS_PURGED", target_type="system", target_id=None,
                          safe_metadata={"deleted": deleted, "legacy_kept": legacy, "grace_hours": grace_hours},
                          request_id=str(uuid.uuid4())))
        db.commit()
        return {"dry_run": False, "planned": planned, "deleted": deleted, "legacy_kept": legacy,
                "grace_hours": grace_hours}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--grace-hours", type=int, default=48)
    args = parser.parse_args()
    print(purge(apply=args.apply, grace_hours=args.grace_hours))
