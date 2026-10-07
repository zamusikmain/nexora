from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from app.audit import audit
from app.auth import Actor, Db, public_user
from app.documents import document_data
from app.models import AuditEvent, Department, Document, DocumentType, User
from app.policy import require, visibility
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
        {"id": t.id, "code": t.code, "name_ru": t.name_ru, "name_en": t.name_en}
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
    visible = visibility(user)
    statuses = db.execute(select(Document.status, func.count()).where(visible).group_by(Document.status))
    types = db.execute(select(Document.type_id, func.count()).where(visible).group_by(Document.type_id))
    recent = db.scalars(select(Document).where(visible).order_by(Document.updated_at.desc()).limit(5))
    return {
        "by_status": dict(statuses.all()),
        "by_type": dict(types.all()),
        "my_documents": db.scalar(
            select(func.count()).select_from(Document).where(Document.owner_id == user.id)
        ),
        "recent": [document_data(d) for d in recent],
    }


@router.get("/audit")
def audit_events(db: Db, user: Actor, page: int = Query(1, ge=1)) -> dict:
    require(user, "audit")
    events = db.scalars(
        select(AuditEvent)
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
                "safe_metadata": a.safe_metadata,
            }
            for a in events
        ],
        "total": db.scalar(select(func.count()).select_from(AuditEvent)),
    }
