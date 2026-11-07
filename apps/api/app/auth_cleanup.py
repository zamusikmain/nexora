"""Operator-run purge of expired sessions and stale login throttles. Dry-run by default.

Both kinds of rows carry no state once expired: current_user rejects expired sessions and
login resets a throttle whose 15-minute window has passed. Deletes run in small batches with
SKIP LOCKED so concurrent logins are never blocked; a row re-armed by a concurrent login is
re-checked by PostgreSQL and kept.
"""

import argparse
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AuditEvent, AuthSession, LoginThrottle

THROTTLE_WINDOW = timedelta(minutes=15)
BATCH = 1000


def _purge(db: Session, model, condition) -> int:
    total = 0
    while True:
        batch = select(model.id).where(condition).limit(BATCH).with_for_update(skip_locked=True)
        deleted = len(db.scalars(delete(model).where(model.id.in_(batch), condition).returning(model.id)).all())
        db.commit()
        total += deleted
        if deleted < BATCH:
            return total


def purge(*, apply: bool = False, grace_hours: int = 24, now: datetime | None = None) -> dict:
    if grace_hours < 1:
        raise ValueError("At least 1 hour grace is required")
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=grace_hours)
    sessions = AuthSession.expires_at < cutoff
    throttles = LoginThrottle.window_start < cutoff - THROTTLE_WINDOW
    with SessionLocal() as db:
        planned = {
            "sessions": db.scalar(select(func.count()).select_from(AuthSession).where(sessions)) or 0,
            "throttles": db.scalar(select(func.count()).select_from(LoginThrottle).where(throttles)) or 0,
        }
        if not apply:
            return {"dry_run": True, "planned": planned, "deleted": None, "grace_hours": grace_hours}
        deleted = {"sessions": _purge(db, AuthSession, sessions), "throttles": _purge(db, LoginThrottle, throttles)}
        db.add(
            AuditEvent(
                actor_id=None,
                action="AUTH_CLEANUP_COMPLETED",
                target_type="system",
                target_id=None,
                safe_metadata={**{f"{k}_deleted": v for k, v in deleted.items()}, "grace_hours": grace_hours},
                request_id=str(uuid.uuid4()),
            )
        )
        db.commit()
        return {"dry_run": False, "planned": planned, "deleted": deleted, "grace_hours": grace_hours}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--grace-hours", type=int, default=24)
    args = parser.parse_args()
    print(purge(apply=args.apply, grace_hours=args.grace_hours))
