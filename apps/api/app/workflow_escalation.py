"""Operator-run escalation of overdue approval tasks. Dry-run by default.

Each overdue task of a running stage is escalated once (approvals.escalated_at): the assignee
gets TASK_OVERDUE, the document owner WORKFLOW_OVERDUE, and the active managers of the
assignee's department TASK_ESCALATED (active administrators when the department has none).
Escalation only informs; it does not reassign or decide anything. Rows are locked with
SKIP LOCKED, so a task that is being decided right now is simply left for the next run.
"""

import argparse
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Approval, AuditEvent, Document, User, WorkflowInstance
from app.notifications import notify

BATCH = 200


def overdue(now: datetime):
    return (
        select(Approval, WorkflowInstance, Document)
        .join(WorkflowInstance, Approval.instance_id == WorkflowInstance.id)
        .join(Document, WorkflowInstance.document_id == Document.id)
        .where(
            Approval.status == "PENDING",
            Approval.escalated_at.is_(None),
            Approval.due_at < now,
            Approval.stage == WorkflowInstance.stage,
            WorkflowInstance.status == "RUNNING",
            Document.deleted_at.is_(None),
        )
    )


def supervisors(db: Session, assignee: User) -> list[str]:
    query = select(User.id).where(User.status == "ACTIVE", User.id != assignee.id)
    managers = list(db.scalars(query.where(User.role == "MANAGER", User.department_id == assignee.department_id)
                               .order_by(User.id).limit(20))) if assignee.department_id else []
    return managers or list(db.scalars(query.where(User.role == "ADMIN").order_by(User.id).limit(20)))


def escalate_one(db: Session, approval: Approval, instance: WorkflowInstance, doc: Document, now: datetime) -> None:
    assignee = db.get(User, approval.user_id)
    assert assignee is not None
    approval.escalated_at = now
    data = {"stage": approval.stage, "due_at": approval.due_at.isoformat() if approval.due_at else None,
            "assignee_id": approval.user_id}
    common: dict[str, Any] = {"document_id": doc.id, "instance_id": instance.id, "data": data}
    notify(db, [approval.user_id], "TASK_OVERDUE", f"TASK_OVERDUE:{approval.id}", approval_id=approval.id, **common)
    notify(db, [doc.owner_id], "WORKFLOW_OVERDUE", f"WORKFLOW_OVERDUE:{approval.id}", **common)
    notified = supervisors(db, assignee)
    notify(db, notified, "TASK_ESCALATED", f"TASK_ESCALATED:{approval.id}", approval_id=approval.id, **common)
    db.add(AuditEvent(actor_id=None, action="WORKFLOW_ESCALATED", target_type="document", target_id=doc.id,
                      safe_metadata={"instance_id": instance.id, "approval_id": approval.id, "stage": approval.stage,
                                     "supervisors_notified": len(notified)},
                      request_id=str(uuid.uuid4())))


def escalate(*, apply: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    with SessionLocal() as db:
        planned = db.scalar(select(func.count()).select_from(overdue(now).subquery())) or 0
        if not apply:
            return {"dry_run": True, "planned": planned, "escalated": None}
        escalated = 0
        while True:
            rows = db.execute(
                overdue(now).order_by(Approval.due_at, Approval.id).limit(BATCH)
                .with_for_update(of=Approval, skip_locked=True)
            ).all()
            for row in rows:
                approval, instance, doc = cast(tuple[Approval, WorkflowInstance, Document], tuple(row))
                escalate_one(db, approval, instance, doc, now)
            db.commit()
            escalated += len(rows)
            if len(rows) < BATCH:
                return {"dry_run": False, "planned": planned, "escalated": escalated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    print(escalate(apply=parser.parse_args().apply))
