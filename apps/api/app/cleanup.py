"""Operator-run orphan sweep. Dry-run by default; never infer absence from a DB error."""

import argparse
import re
import time
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, DocumentVersion
from app.storage import storage


def candidates(store, referenced: set[str], older_than: float) -> list:
    result = []
    for path in store.root.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        name = path.name
        quarantine = re.fullmatch(r"\.quarantine-[a-f0-9]{32}", name)
        orphan = re.fullmatch(r"[a-f0-9]{32}", name) and name not in referenced
        if (quarantine or orphan) and path.stat().st_mtime < older_than:
            result.append(path)
    return result


def sweep(*, apply: bool = False, grace_hours: int = 48) -> dict:
    if grace_hours < 24:
        raise ValueError("At least 24 hours grace is required")
    # Materialize a complete successful DB result before looking at any filesystem candidates.
    with SessionLocal() as db:
        referenced = set(db.scalars(select(DocumentVersion.storage_key)).all())
        if any(not re.fullmatch(r"[a-f0-9]{32}", key) for key in referenced):
            raise ValueError("Unexpected database storage key; cleanup aborted")
        store = storage()
        cutoff = time.time() - grace_hours * 3600
        planned = candidates(store, referenced, cutoff)
        if not apply:
            return {"dry_run": True, "candidates": len(planned), "deleted": 0, "grace_hours": grace_hours}
        request_id = str(uuid.uuid4())
        db.add(
            AuditEvent(
                actor_id=None,
                action="ORPHAN_CLEANUP_STARTED",
                target_type="storage",
                target_id=None,
                safe_metadata={"count": len(planned), "grace_hours": grace_hours},
                request_id=request_id,
            )
        )
        db.commit()  # If DB or audit fails, zero filesystem deletes have occurred.
        deleted = 0
        for path in planned:
            # Re-check age/type; do not follow links or remove referenced version keys.
            if path.is_symlink() or not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            if path.name in referenced:
                continue
            path.unlink()
            deleted += 1
        db.add(
            AuditEvent(
                actor_id=None,
                action="ORPHAN_CLEANUP_COMPLETED",
                target_type="storage",
                target_id=None,
                safe_metadata={"count": deleted, "grace_hours": grace_hours},
                request_id=request_id,
            )
        )
        db.commit()
        return {"dry_run": False, "candidates": len(planned), "deleted": deleted, "grace_hours": grace_hours}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--grace-hours", type=int, default=48)
    args = parser.parse_args()
    print(sweep(apply=args.apply, grace_hours=args.grace_hours))
