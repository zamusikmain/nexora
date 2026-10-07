"""Transactional sequential stages with parallel unanimous decisions."""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.audit import audit
from app.auth import Actor, Db
from app.documents import get_document
from app.models import Approval, Department, Document, User, WorkflowEvent, WorkflowInstance, WorkflowTemplate
from app.policy import require
from app.schemas import Input

router = APIRouter(tags=["workflows"])


class Condition(Input):
    field: str = Field(pattern=r"^(confidentiality|metadata\.[a-z][a-z0-9_]{0,39})$")
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]
    value: Any

    @model_validator(mode="after")
    def valid_condition(self):
        scalars = self.value if isinstance(self.value, list) else [self.value]
        if any(
            (type(v) is float and not math.isfinite(v)) or (isinstance(v, str) and len(v) > 240)
            for v in scalars
        ):
            raise ValueError("invalid_condition")
        if self.op in {"gt", "gte", "lt", "lte"} and (
            type(self.value) not in {int, float}
            or (type(self.value) is float and not math.isfinite(self.value))
        ):
            raise ValueError("numeric_condition_required")
        if self.op == "in" and (
            not isinstance(self.value, list)
            or len(self.value) > 100
            or any(type(v) not in {str, int, float, bool} for v in self.value)
        ):
            raise ValueError("invalid_condition")
        if self.op in {"eq", "ne"} and type(self.value) not in {str, int, float, bool, type(None)}:
            raise ValueError("invalid_condition")
        return self


class Stage(Input):
    name_ru: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)
    selector: Literal["user", "role", "department"]
    targets: list[str] = Field(min_length=1, max_length=50)
    due_hours: int = Field(default=72, ge=1, le=720)
    require_comment: bool = False
    conditions: list[Condition] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def valid_targets(self):
        if len(set(self.targets)) != len(self.targets) or any(not x or len(x) > 36 for x in self.targets):
            raise ValueError("invalid_targets")
        if self.selector == "role" and any(
            x not in {"USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN"} for x in self.targets
        ):
            raise ValueError("invalid_role")
        return self


class TemplateInput(Input):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,39}$")
    name_ru: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    stages: list[Stage] = Field(min_length=1, max_length=20)


class Start(Input):
    template_id: str = Field(min_length=1, max_length=36)
    expected_revision: int = Field(ge=1)
    idempotency_key: UUID


class Decision(Input):
    action: Literal["approve", "reject", "revision", "cancel"]
    comment: str = Field(default="", max_length=2000)
    idempotency_key: UUID


def template_data(t: WorkflowTemplate) -> dict:
    return {
        "id": t.id,
        "code": t.code,
        "version": t.version,
        "name_ru": t.name_ru,
        "name_en": t.name_en,
        "stages": t.definition["stages"],
        "created_at": t.created_at,
    }


@router.get("/workflow-templates")
def templates(db: Db, user: Actor) -> list[dict]:
    # Select latest versions in SQL; history is retained and bound instances keep their original version.
    latest = (
        select(WorkflowTemplate.code, func.max(WorkflowTemplate.version).label("version"))
        .group_by(WorkflowTemplate.code)
        .subquery()
    )
    return [
        template_data(t)
        for t in db.scalars(
            select(WorkflowTemplate)
            .join(
                latest,
                (WorkflowTemplate.code == latest.c.code) & (WorkflowTemplate.version == latest.c.version),
            )
            .order_by(WorkflowTemplate.code)
            .limit(100)
        )
    ]


@router.post("/workflow-templates", status_code=201)
def create_template(body: TemplateInput, request: Request, db: Db, user: Actor) -> dict:
    require(user, "admin")
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "template:" + body.code}
    )
    for stage in body.stages:
        if stage.selector in {"user", "department"}:
            model = User if stage.selector == "user" else Department
            count = db.scalar(select(func.count()).select_from(model).where(model.id.in_(stage.targets)))
            if count != len(stage.targets):
                raise HTTPException(422, "invalid_workflow_target")
    version = (
        db.scalar(select(func.max(WorkflowTemplate.version)).where(WorkflowTemplate.code == body.code)) or 0
    ) + 1
    row = WorkflowTemplate(
        code=body.code,
        version=version,
        name_ru=body.name_ru,
        name_en=body.name_en,
        definition={"stages": [s.model_dump() for s in body.stages]},
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    audit(
        db, request, user.id, "WORKFLOW_TEMPLATE_CREATED", "workflow_template", row.id, {"version": version}
    )
    db.commit()
    return template_data(row)


def matches(condition: Condition, snapshot: dict) -> bool:
    value = (
        snapshot.get("confidentiality")
        if condition.field == "confidentiality"
        else snapshot["metadata"].get(condition.field.split(".")[1])
    )
    if condition.op == "eq":
        return type(value) is type(condition.value) and value == condition.value
    if condition.op == "ne":
        return not (type(value) is type(condition.value) and value == condition.value)
    if condition.op == "in":
        return any(type(value) is type(v) and value == v for v in condition.value)
    if type(value) not in {int, float}:
        return False
    return {
        "gt": lambda: value > condition.value,
        "gte": lambda: value >= condition.value,
        "lt": lambda: value < condition.value,
        "lte": lambda: value <= condition.value,
    }[condition.op]()


def request_hash(instance_or_doc: str, body: Input) -> str:
    payload = {"target": instance_or_doc, "body": body.model_dump(mode="json", exclude={"idempotency_key"})}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def previous(db: Db, user: Actor, key: UUID, fingerprint: str) -> WorkflowEvent | None:
    event = db.scalar(
        select(WorkflowEvent).where(
            WorkflowEvent.actor_id == user.id, WorkflowEvent.idempotency_key == str(key)
        )
    )
    if event and event.request_hash != fingerprint:
        raise HTTPException(409, "idempotency_conflict")
    return event


def instance_data(instance: WorkflowInstance, db: Db, user: Actor) -> dict:
    template = db.get(WorkflowTemplate, instance.template_id)
    assert template is not None
    stages = template.definition["stages"]
    assignments = list(
        db.scalars(
            select(Approval).where(Approval.instance_id == instance.id).order_by(Approval.stage, Approval.id)
        )
    )
    events = list(
        db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.instance_id == instance.id)
            .order_by(WorkflowEvent.created_at, WorkflowEvent.id)
        )
    )
    actor_ids = {a.user_id for a in assignments} | {e.actor_id for e in events}
    names = dict(db.execute(select(User.id, User.display_name).where(User.id.in_(actor_ids))).all())
    return {
        "id": instance.id,
        "document_id": instance.document_id,
        "document_version_id": instance.document_version_id,
        "template": template_data(template),
        "status": instance.status,
        "stage": instance.stage,
        "created_at": instance.created_at,
        "completed_at": instance.completed_at,
        "approvals": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "display_name": names.get(a.user_id, a.user_id),
                "stage": a.stage,
                "status": a.status,
                "due_at": a.due_at,
                "acted_at": a.acted_at,
                "name_ru": stages[a.stage]["name_ru"],
                "name_en": stages[a.stage]["name_en"],
                "mine": a.user_id == user.id,
            }
            for a in assignments
        ],
        "events": [
            {
                "id": e.id,
                "actor_id": e.actor_id,
                "display_name": names.get(e.actor_id, e.actor_id),
                "action": e.action,
                "comment": e.comment,
                "previous_state": e.previous_state,
                "new_state": e.new_state,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


def commit_event(
    db: Db,
    request: Request,
    user: Actor,
    instance: WorkflowInstance,
    action: str,
    comment: str,
    key: UUID,
    fingerprint: str,
    previous_state: str,
):
    db.add(
        WorkflowEvent(
            instance_id=instance.id,
            actor_id=user.id,
            action=action,
            comment=comment,
            previous_state=previous_state,
            new_state=instance.status,
            idempotency_key=str(key),
            request_hash=fingerprint,
        )
    )
    audit(
        db,
        request,
        user.id,
        "WORKFLOW_" + action,
        "document",
        instance.document_id,
        {"instance_id": instance.id, "status": instance.status, "stage": instance.stage},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "idempotency_conflict") from None


@router.get("/documents/{doc_id}/workflows")
def document_workflows(doc_id: str, db: Db, user: Actor) -> list[dict]:
    get_document(db, user, doc_id)
    return [
        instance_data(i, db, user)
        for i in db.scalars(
            select(WorkflowInstance)
            .where(WorkflowInstance.document_id == doc_id)
            .order_by(WorkflowInstance.created_at.desc())
            .limit(20)
        )
    ]


@router.post("/documents/{doc_id}/workflows", status_code=201)
def start(doc_id: str, body: Start, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    if doc.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(403, "forbidden")
    fingerprint = request_hash(doc_id, body)
    event = previous(db, user, body.idempotency_key, fingerprint)
    if event:
        restored = db.get(WorkflowInstance, event.instance_id)
        assert restored is not None
        return instance_data(restored, db, user)
    if doc.revision != body.expected_revision:
        raise HTTPException(409, "stale_document")
    if doc.deleted_at or doc.status not in {"DRAFT", "SUBMITTED", "REVISION_REQUIRED"}:
        raise HTTPException(409, "invalid_transition")
    if not doc.current_version_id:
        raise HTTPException(409, "file_required")
    template = db.get(WorkflowTemplate, body.template_id)
    if template is None:
        raise HTTPException(422, "invalid_workflow_template")
    snapshot = {
        "metadata": doc.business_metadata,
        "confidentiality": doc.confidentiality,
        "title": doc.title,
        "revision": doc.revision,
    }
    plan = []
    for index, data in enumerate(template.definition["stages"]):
        stage = Stage.model_validate(data)
        if not all(matches(c, snapshot) for c in stage.conditions):
            continue
        query = select(User.id).where(User.status == "ACTIVE", User.id != doc.owner_id)
        if stage.selector == "user":
            query = query.where(User.id.in_(stage.targets))
        elif stage.selector == "role":
            query = query.where(User.role.in_(stage.targets))
        else:
            query = query.where(User.department_id.in_(stage.targets))
        users = list(db.scalars(query.order_by(User.id).limit(101)))
        if not users or len(users) > 100:
            raise HTTPException(422, "invalid_workflow_target")
        plan.append((index, stage, users))
    if sum(len(users) for _, _, users in plan) > 200:
        raise HTTPException(422, "invalid_workflow_target")
    if not plan:
        raise HTTPException(422, "empty_workflow")
    instance = WorkflowInstance(
        document_id=doc.id,
        document_version_id=doc.current_version_id,
        template_id=template.id,
        metadata_snapshot=snapshot,
        started_by=user.id,
        stage=plan[0][0],
    )
    db.add(instance)
    db.flush()
    for index, stage, users in plan:
        for user_id in users:
            active = index == instance.stage
            db.add(
                Approval(
                    instance_id=instance.id,
                    stage=index,
                    user_id=user_id,
                    status="PENDING" if active else "WAITING",
                    due_at=datetime.now(UTC) + timedelta(hours=stage.due_hours) if active else None,
                )
            )
    doc.status = "IN_APPROVAL"
    doc.revision += 1
    commit_event(db, request, user, instance, "STARTED", "", body.idempotency_key, fingerprint, "NONE")
    return instance_data(instance, db, user)


@router.post("/workflows/{instance_id}/decisions")
def decide(instance_id: str, body: Decision, request: Request, db: Db, user: Actor) -> dict:
    # Same lock ordering for start, decisions, document edits and cancellation.
    row = db.get(WorkflowInstance, instance_id)
    if row is None:
        raise HTTPException(404, "not_found")
    doc = get_document(db, user, row.document_id, lock=True)
    instance = db.scalar(select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update())
    assert instance is not None
    fingerprint = request_hash(instance_id, body)
    event = previous(db, user, body.idempotency_key, fingerprint)
    if event:
        return instance_data(instance, db, user)
    if instance.status != "RUNNING":
        raise HTTPException(409, "workflow_not_running")
    approvals = list(
        db.scalars(
            select(Approval)
            .where(Approval.instance_id == instance.id)
            .order_by(Approval.id)
            .with_for_update()
        )
    )
    mine = next((a for a in approvals if a.user_id == user.id and a.stage == instance.stage), None)
    if body.action == "cancel":
        if doc.owner_id != user.id and user.role != "ADMIN":
            raise HTTPException(403, "forbidden")
    elif mine is None or mine.status != "PENDING":
        raise HTTPException(403, "not_assigned_approval")
    template = db.get(WorkflowTemplate, instance.template_id)
    assert template is not None
    stage = Stage.model_validate(template.definition["stages"][instance.stage])
    if (body.action != "approve" or stage.require_comment) and not body.comment:
        raise HTTPException(422, "approval_comment_required")
    old = instance.status
    if body.action == "approve":
        assert mine is not None
        mine.status = "APPROVED"
        mine.acted_at = datetime.now(UTC)
        if not any(a.stage == instance.stage and a.status == "PENDING" for a in approvals):
            following = sorted({a.stage for a in approvals if a.status == "WAITING"})
            if following:
                instance.stage = following[0]
                next_stage = Stage.model_validate(template.definition["stages"][instance.stage])
                for approval in approvals:
                    if approval.stage == instance.stage:
                        approval.status = "PENDING"
                        approval.due_at = datetime.now(UTC) + timedelta(hours=next_stage.due_hours)
            else:
                instance.status = "APPROVED"
    else:
        instance.status = {"reject": "REJECTED", "revision": "REVISION_REQUIRED", "cancel": "CANCELLED"}[
            body.action
        ]
        if mine is not None and body.action != "cancel":
            mine.status = instance.status
            mine.acted_at = datetime.now(UTC)
        for approval in approvals:
            if approval.status in {"WAITING", "PENDING"}:
                approval.status = "CANCELLED"
    if instance.status != "RUNNING":
        instance.completed_at = datetime.now(UTC)
        doc.status = instance.status
    doc.revision += 1
    commit_event(
        db,
        request,
        user,
        instance,
        {"approve": "APPROVED", "reject": "REJECTED", "revision": "RETURNED", "cancel": "CANCELLED"}[
            body.action
        ],
        body.comment,
        body.idempotency_key,
        fingerprint,
        old,
    )
    return instance_data(instance, db, user)


@router.get("/approvals")
def my_approvals(
    db: Db,
    user: Actor,
    view: Literal["pending", "completed", "rejected", "overdue"] = "pending",
    page: int = Query(1, ge=1),
) -> dict:
    conditions = [Approval.user_id == user.id, Document.deleted_at.is_(None)]
    if view in {"pending", "overdue"}:
        conditions.append(Approval.status == "PENDING")
    elif view == "completed":
        conditions.append(Approval.status == "APPROVED")
    else:
        conditions.append(Approval.status.in_(["REJECTED", "REVISION_REQUIRED"]))
    if view == "overdue":
        conditions.append(Approval.due_at < datetime.now(UTC))
    base = (
        select(Approval, WorkflowInstance, Document)
        .join(WorkflowInstance, Approval.instance_id == WorkflowInstance.id)
        .join(Document, WorkflowInstance.document_id == Document.id)
        .where(*conditions)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(
        base.order_by(Approval.due_at.asc().nulls_last(), Approval.id).offset((page - 1) * 25).limit(25)
    )
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": a.id,
                "instance_id": i.id,
                "document_id": d.id,
                "title": d.title,
                "number": d.number,
                "stage": a.stage,
                "status": a.status,
                "due_at": a.due_at,
            }
            for a, i, d in rows
        ],
    }
