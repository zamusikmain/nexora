"""In-app notifications. Rows are written in the same transaction as the change that caused them.

A row stores identifiers only. Document number and title are resolved when the recipient reads
the list, through the same ACL as everywhere else, so a notification never shows more than its
recipient may read right now. The table is also the email outbox (app.notification_dispatch).
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import Actor, Db
from app.config import settings
from app.models import Approval, Document, Notification, User, uid
from app.policy import can_read

router = APIRouter(tags=["notifications"])
PAGE = 20
TASK_KINDS = {"TASK_ASSIGNED", "TASK_OVERDUE"}
OWNER_KINDS = {"WORKFLOW_APPROVED", "WORKFLOW_REJECTED", "WORKFLOW_RETURNED", "WORKFLOW_OVERDUE"}


def notify(
    db: Session,
    recipients: Iterable[str],
    kind: str,
    dedupe: str,
    *,
    document_id: str,
    instance_id: str | None = None,
    approval_id: str | None = None,
    actor_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> int:
    """Insert one notification per recipient; a repeated dedupe key for a recipient is ignored."""
    rows = [
        {
            "id": uid(),
            "recipient_id": recipient,
            "kind": kind,
            "document_id": document_id,
            "instance_id": instance_id,
            "approval_id": approval_id,
            "actor_id": actor_id,
            "data": data or {},
            "dedupe_key": dedupe,
            "email_status": "PENDING" if settings().smtp_host else "NONE",
        }
        for recipient in sorted(set(recipients))
        if recipient != actor_id  # nobody is notified about their own action
    ]
    if not rows:
        return 0
    db.flush()
    result = db.execute(
        insert(Notification).values(rows).on_conflict_do_nothing(constraint="uq_notification_dedupe")
        .returning(Notification.id)
    )
    return len(result.all())


def notification_data(db: Session, user: User, row: Notification, doc: Document,
                      approval: Approval | None, names: dict[str, str]) -> dict:
    visible = can_read(db, user, doc, "card")
    if row.kind in TASK_KINDS and approval is not None and approval.status == "PENDING":
        href: str | None = f"/approvals/{approval.id}/review"
    elif row.kind in TASK_KINDS or row.kind == "TASK_CANCELLED":
        href = "/approvals"
    elif row.kind in OWNER_KINDS and visible:
        href = f"/documents/{doc.id}"
    else:
        href = None
    data = dict(row.data or {})
    if "assignee_id" in data:
        data["assignee_name"] = names.get(data["assignee_id"], "")
    return {
        "id": row.id,
        "kind": row.kind,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "href": href,
        "actor_name": names.get(row.actor_id or "", None),
        "document": {"id": doc.id, "number": doc.number, "title": doc.title} if visible else None,
        "data": data,
    }


def unread_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
    ) or 0


@router.get("/notifications")
def list_notifications(db: Db, user: Actor, unread: bool = False, page: int = Query(1, ge=1, le=500)) -> dict:
    conditions = [Notification.recipient_id == user.id]
    if unread:
        conditions.append(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
    rows = list(db.scalars(
        select(Notification).where(*conditions)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * PAGE).limit(PAGE)
    ))
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_({r.document_id for r in rows})))}
    approvals = {a.id: a for a in db.scalars(
        select(Approval).where(Approval.id.in_({r.approval_id for r in rows if r.approval_id})))}
    people = {r.actor_id for r in rows if r.actor_id} | {
        r.data["assignee_id"] for r in rows if isinstance(r.data, dict) and r.data.get("assignee_id")}
    names = dict(db.execute(select(User.id, User.display_name).where(User.id.in_(people))).all()) if people else {}
    return {
        "total": total,
        "unread": unread_count(db, user),
        "page": page,
        "items": [notification_data(db, user, r, docs[r.document_id], approvals.get(r.approval_id or ""), names)
                  for r in rows],
    }


@router.get("/notifications/summary")
def summary(db: Db, user: Actor) -> dict:
    return {"unread": unread_count(db, user)}


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: str, db: Db, user: Actor) -> Response:
    found = db.scalar(select(Notification.id).where(
        Notification.id == notification_id, Notification.recipient_id == user.id))
    if found is None:
        raise HTTPException(404, "not_found")
    db.execute(update(Notification).where(
        Notification.id == notification_id, Notification.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    db.commit()
    return Response(status_code=204)


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(db: Db, user: Actor) -> Response:
    db.execute(update(Notification).where(
        Notification.recipient_id == user.id, Notification.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    db.commit()
    return Response(status_code=204)
