from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, select

from app.audit import audit
from app.auth import Actor, Db, public_user
from app.custom_fields import TypeInput
from app.documents import document_projection
from app.models import AuditEvent, Department, Document, DocumentType, User
from app.policy import require, visibility, visible_field
from app.schemas import UserOut, UserUpdate

router = APIRouter(tags=["catalog"])


@router.get("/departments")
def departments(db: Db, user: Actor) -> list[dict]:
    return [
        {"id": d.id, "code": d.code, "name_ru": d.name_ru, "name_en": d.name_en}
        for d in db.scalars(select(Department).order_by(Department.code))
    ]


@router.get("/document-types")
def types(db: Db, user: Actor) -> list[dict]:
    return [
        {
            "id": t.id,
            "code": t.code,
            "name_ru": t.name_ru,
            "name_en": t.name_en,
            "metadata_schema": t.metadata_schema,
        }
        for t in db.scalars(select(DocumentType).order_by(DocumentType.code))
    ]


@router.get("/users", response_model=list[UserOut])
def users(db: Db, user: Actor) -> list[dict]:
    require(user, "admin")
    return [public_user(u) for u in db.scalars(select(User).order_by(User.email).limit(500))]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, request: Request, db: Db, user: Actor) -> dict:
    require(user, "admin")
    if user_id == user.id:
        raise HTTPException(409, "self_admin_change")
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not target:
        raise HTTPException(404, "not_found")
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(422, "invalid_department")
    target.role, target.status, target.department_id = body.role, body.status, body.department_id
    audit(
        db,
        request,
        user.id,
        "USER_UPDATED",
        "user",
        target.id,
        {"role": target.role, "status": target.status, "department_id": target.department_id},
    )
    db.commit()
    return public_user(target)


@router.get("/dashboard")
def dashboard(db: Db, user: Actor) -> dict:
    visible = visibility(user) & Document.deleted_at.is_(None)
    status_field = visible_field(user, "status")
    statuses = db.execute(select(status_field, func.count()).where(visible).group_by(status_field))
    types = db.execute(select(Document.type_id, func.count()).where(visible).group_by(Document.type_id))
    recent = db.scalars(select(Document).where(visible).order_by(Document.updated_at.desc()).limit(5))
    return {
        "by_status": dict(statuses.all()),
        "by_type": dict(types.all()),
        "my_documents": db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == user.id, Document.deleted_at.is_(None))
        ),
        "recent": [document_projection(db, user, d) for d in recent],
    }


@router.get("/audit")
def audit_events(db: Db, user: Actor, page: int = Query(1, ge=1)) -> dict:
    require(user, "audit")
    visible = or_(AuditEvent.target_type != "document", AuditEvent.target_id.in_(
        select(Document.id).where(Document.owner_id == user.id),
    ))
    events = db.scalars(
        select(AuditEvent)
        .where(visible)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .offset((page - 1) * 50)
        .limit(50)
    )
    return {
        "items": [
            {
                "id": a.id,
                "action": a.action,
                "actor_id": a.actor_id,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "created_at": a.created_at,
                "request_id": a.request_id,
                "safe_metadata": a.safe_metadata if a.target_type not in {"access_grant", "approval"} else {},
            }
            for a in events
        ],
        "total": db.scalar(select(func.count()).select_from(AuditEvent).where(visible)),
    }


@router.post("/document-types", status_code=201)
def create_type(body: TypeInput, request: Request, db: Db, user: Actor) -> dict:
    require(user, "admin")
    from sqlalchemy.exc import IntegrityError

    row = DocumentType(
        code=body.code,
        name_ru=body.name_ru,
        name_en=body.name_en,
        metadata_schema={"fields": [f.model_dump() for f in body.fields]},
    )
    db.add(row)
    try:
        db.flush()
        audit(db, request, user.id, "DOCUMENT_TYPE_CREATED", "document_type", row.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "duplicate_code") from None
    return {
        "id": row.id,
        "code": row.code,
        "name_ru": row.name_ru,
        "name_en": row.name_en,
        "metadata_schema": row.metadata_schema,
    }


@router.patch("/document-types/{type_id}")
def update_type(type_id: str, body: TypeInput, request: Request, db: Db, user: Actor) -> dict:
    require(user, "admin")
    from sqlalchemy.exc import IntegrityError

    row = db.scalar(select(DocumentType).where(DocumentType.id == type_id).with_for_update())
    if row is None:
        raise HTTPException(404, "not_found")
    old_keys = {f["key"] for f in row.metadata_schema.get("fields", [])}
    new_keys = {f.key for f in body.fields}
    if old_keys - new_keys and db.scalar(select(Document.id).where(Document.type_id == row.id).limit(1)):
        raise HTTPException(409, "field_in_use")
    row.code, row.name_ru, row.name_en = body.code, body.name_ru, body.name_en
    row.metadata_schema = {"fields": [f.model_dump() for f in body.fields]}
    try:
        audit(db, request, user.id, "DOCUMENT_TYPE_UPDATED", "document_type", row.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "duplicate_code") from None
    return {
        "id": row.id,
        "code": row.code,
        "name_ru": row.name_ru,
        "name_en": row.name_en,
        "metadata_schema": row.metadata_schema,
    }
