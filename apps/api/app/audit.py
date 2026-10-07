from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditEvent


def audit(
    db: Session,
    request: Request,
    actor_id: str | None,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            safe_metadata=metadata or {},
            request_id=request.state.request_id,
        )
    )
