"""Confirm legacy immutable bytes with the configured ClamAV scanner; never delete versions."""

import argparse
import hashlib
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.db import SessionLocal
from app.models import AuditEvent, DocumentVersion, FileScan
from app.scanning import scanner
from app.storage import storage


def scan_legacy(*, apply: bool = False) -> dict:
    if settings().malware_scanner != "clamav":
        raise ValueError("Legacy attestation requires ClamAV")
    verified = blocked = 0
    cursor = ""
    store = storage()
    while True:
        with SessionLocal() as db:
            rows = list(
                db.scalars(
                    select(DocumentVersion)
                    .outerjoin(FileScan, DocumentVersion.id == FileScan.version_id)
                    .where(FileScan.version_id.is_(None), DocumentVersion.id > cursor)
                    .order_by(DocumentVersion.id)
                    .limit(100)
                )
            )
            if not rows:
                break
            if not apply:
                return {"dry_run": True, "unscanned_sample": len(rows), "sample_limit": 100}
            for version in rows:
                cursor = version.id
                try:
                    path = store.path(version.storage_key)
                    checksum = hashlib.sha256()
                    size = 0
                    with path.open("rb") as file:
                        while chunk := file.read(64 * 1024):
                            size += len(chunk)
                            if size > version.size:
                                raise ValueError("Size mismatch")
                            checksum.update(chunk)
                    if size != version.size or checksum.hexdigest() != version.sha256:
                        raise ValueError("Integrity mismatch")
                    scanner().scan(path)
                    db.execute(
                        insert(FileScan)
                        .values(version_id=version.id, sha256=version.sha256, engine="clamav")
                        .on_conflict_do_nothing()
                    )
                    action = "FILE_SCAN_CONFIRMED"
                    verified += 1
                except (HTTPException, OSError, ValueError):
                    action = "FILE_SCAN_BLOCKED"
                    blocked += 1
                db.add(
                    AuditEvent(
                        actor_id=None,
                        action=action,
                        target_type="document",
                        target_id=version.document_id,
                        safe_metadata={"version_id": version.id},
                        request_id=str(uuid.uuid4()),
                    )
                )
                db.commit()
    return {"dry_run": not apply, "verified": verified, "blocked": blocked}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(scan_legacy(apply=args.apply))
