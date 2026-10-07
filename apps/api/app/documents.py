from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.audit import audit
from app.auth import Actor, Db
from app.custom_fields import validate_metadata
from app.models import (
    AuditEvent,
    Comment,
    Document,
    DocumentType,
    DocumentVersion,
    Favorite,
    User,
    number_sequence,
)
from app.policy import can_read, require, require_write, visibility
from app.schemas import (
    CommentCreate,
    CommentOut,
    DocumentCreate,
    DocumentListOut,
    DocumentMetadata,
    DocumentOut,
    DocumentUpdate,
    Transition,
    VersionOut,
)
from app.storage import storage

router = APIRouter(prefix="/documents", tags=["documents"])


def document_data(doc: Document) -> dict[str, Any]:
    return {
        **{
            key: getattr(doc, key)
            for key in (
                "description",
                "category",
                "tags",
                "responsible_id",
                "confidentiality",
                "effective_date",
                "expiration_date",
            )
        },
        "id": doc.id,
        "folder_id": doc.folder_id,
        "deleted_at": doc.deleted_at,
        "revision": doc.revision,
        "number": doc.number,
        "title": doc.title,
        "type_id": doc.type_id,
        "owner_id": doc.owner_id,
        "department_id": doc.department_id,
        "status": doc.status,
        "business_metadata": doc.business_metadata,
        "current_version_id": doc.current_version_id,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def get_document(db: Db, user: Actor, doc_id: str, lock: bool = False) -> Document:
    query = select(Document).where(Document.id == doc_id)
    if lock:
        query = query.with_for_update()
    doc = db.scalar(query)
    if not doc or (
        not can_read(user, doc)
        and not db.scalar(select(Document.id).where(Document.id == doc_id, visibility(user)))
    ):
        raise HTTPException(404, "not_found")
    return doc


@router.get("", response_model=DocumentListOut)
def list_documents(
    db: Db,
    user: Actor,
    q: str = Query("", max_length=240),
    view: str = Query("all", pattern="^(all|my|favorites|archive|trash)$"),
    folder_id: str | None = None,
    status: str | None = None,
    type_id: str | None = None,
    department_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    conditions = [
        visibility(user),
        Document.deleted_at.is_not(None) if view == "trash" else Document.deleted_at.is_(None),
    ]
    if view == "my":
        conditions.append(Document.owner_id == user.id)
    elif view == "favorites":
        conditions.append(Document.id.in_(select(Favorite.document_id).where(Favorite.user_id == user.id)))
    elif view == "archive":
        conditions.append(Document.status == "ARCHIVED")
    if folder_id:
        conditions.append(Document.folder_id == folder_id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            or_(
                Document.title.ilike(f"%{escaped}%", escape="\\"),
                Document.number.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    for column, value in [
        (Document.status, status),
        (Document.type_id, type_id),
        (Document.department_id, department_id),
    ]:
        if value:
            conditions.append(column == value)
    total = db.scalar(select(func.count()).select_from(Document).where(*conditions))
    docs = db.scalars(
        select(Document)
        .where(*conditions)
        .order_by(Document.updated_at.desc(), Document.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": [document_data(d) for d in docs], "total": total, "page": page}


def metadata_values(body, db: Db) -> dict:
    values = body.model_dump(
        include={
            "description",
            "category",
            "tags",
            "responsible_id",
            "confidentiality",
            "effective_date",
            "expiration_date",
        }
    )
    if values["responsible_id"]:
        responsible = db.get(User, values["responsible_id"])
        if responsible is None or responsible.status != "ACTIVE":
            raise HTTPException(422, "invalid_responsible")
    return values


@router.post("", status_code=201, response_model=DocumentOut)
def create_document(body: DocumentCreate, request: Request, db: Db, user: Actor) -> dict:
    require(user, "create")
    doc_type = db.get(DocumentType, body.type_id)
    if not doc_type:
        raise HTTPException(422, "invalid_document_type")
    metadata = metadata_values(body, db)
    sequence = db.scalar(number_sequence.next_value())
    doc = Document(
        **metadata,
        number=f"DOC-{datetime.now(UTC).year}-{sequence:06d}",
        title=body.title,
        type_id=body.type_id,
        owner_id=user.id,
        department_id=user.department_id,
        business_metadata=validate_metadata(doc_type.metadata_schema, body.business_metadata, db),
    )
    db.add(doc)
    db.flush()
    audit(db, request, user.id, "DOCUMENT_CREATED", "document", doc.id)
    db.commit()
    return document_data(doc)


@router.get("/{doc_id}", response_model=DocumentOut)
def read_document(doc_id: str, db: Db, user: Actor) -> dict:
    return document_data(get_document(db, user, doc_id))


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: str, body: DocumentUpdate, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require_write(user, doc)
    if body.expected_revision is not None and body.expected_revision != doc.revision:
        raise HTTPException(409, "stale_document")
    doc_type = db.get(DocumentType, doc.type_id)
    if doc_type is None:
        raise HTTPException(422, "invalid_document_type")
    supplied = metadata_values(body, db)
    merged = {key: supplied[key] if key in body.model_fields_set else getattr(doc, key) for key in supplied}
    try:
        DocumentMetadata.model_validate(merged)
    except ValueError:
        raise HTTPException(422, "invalid_dates") from None
    for key, value in supplied.items():
        if key in body.model_fields_set:
            setattr(doc, key, value)
    doc.revision += 1
    doc.title, doc.business_metadata = (
        body.title,
        validate_metadata(doc_type.metadata_schema, body.business_metadata, db),
    )
    audit(db, request, user.id, "DOCUMENT_UPDATED", "document", doc.id)
    db.commit()
    return document_data(doc)


@router.post("/{doc_id}/transitions", response_model=DocumentOut)
def transition(doc_id: str, body: Transition, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    if doc.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(403, "forbidden")
    if doc.deleted_at is not None:
        raise HTTPException(409, "document_in_trash")
    targets = {
        "submit": ({"DRAFT", "REVISION_REQUIRED"}, "SUBMITTED"),
        "cancel": ({"DRAFT", "SUBMITTED", "REVISION_REQUIRED"}, "CANCELLED"),
        "archive": ({"CANCELLED", "APPROVED", "REJECTED"}, "ARCHIVED"),
    }
    states, target = targets[body.action]
    if doc.status not in states:
        raise HTTPException(409, "invalid_transition")
    if body.action == "submit" and not doc.current_version_id:
        raise HTTPException(409, "file_required")
    doc.revision += 1
    previous, doc.status = doc.status, target
    audit(
        db,
        request,
        user.id,
        "DOCUMENT_" + {"submit": "SUBMITTED", "cancel": "CANCELLED", "archive": "ARCHIVED"}[body.action],
        "document",
        doc.id,
        {"from": previous, "to": target},
    )
    db.commit()
    return document_data(doc)


@router.get("/{doc_id}/versions", response_model=list[VersionOut])
def versions(doc_id: str, db: Db, user: Actor) -> list[dict]:
    get_document(db, user, doc_id)
    return [
        version_data(v)
        for v in db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_number.desc())
        )
    ]


def version_data(v: DocumentVersion) -> dict:
    return {
        "id": v.id,
        "document_id": v.document_id,
        "version_number": v.version_number,
        "original_filename": v.original_filename,
        "mime_type": v.mime_type,
        "size": v.size,
        "sha256": v.sha256,
        "created_at": v.created_at,
        "created_by": v.created_by,
        "change_note": v.change_note,
    }


@router.post("/{doc_id}/versions", status_code=201, response_model=VersionOut)
def upload_version(
    doc_id: str,
    request: Request,
    db: Db,
    user: Actor,
    file: UploadFile = File(),
    change_note: str = Form("", max_length=1000),
) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require_write(user, doc)
    store = storage()
    saved = store.save(file)
    try:
        last = (
            db.scalar(
                select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == doc.id)
            )
            or 0
        )
        version = DocumentVersion(
            document_id=doc.id,
            version_number=last + 1,
            original_filename=saved.name,
            storage_key=saved.key,
            mime_type=saved.mime,
            size=saved.size,
            sha256=saved.sha256,
            created_by=user.id,
            change_note=change_note or None,
        )
        db.add(version)
        db.flush()
        doc.current_version_id = version.id
        doc.revision += 1
        doc.updated_at = datetime.now(UTC)
        audit(db, request, user.id, "FILE_UPLOADED", "document", doc.id, {"version": last + 1})
        audit(db, request, user.id, "VERSION_CREATED", "document", doc.id, {"version_id": version.id})
        db.commit()
    except Exception:
        db.rollback()
        # A lost commit acknowledgement can leave a committed version. Keep the blob
        # until a DB-confirmed orphan sweep; deleting here could destroy valid data.
        raise
    return version_data(version)


@router.get("/{doc_id}/versions/{version_id}/download")
def download(doc_id: str, version_id: str, request: Request, db: Db, user: Actor) -> StreamingResponse:
    get_document(db, user, doc_id)
    version = db.scalar(
        select(DocumentVersion).where(DocumentVersion.id == version_id, DocumentVersion.document_id == doc_id)
    )
    if not version:
        raise HTTPException(404, "not_found")
    try:
        file = storage().open(version.storage_key)
    except FileNotFoundError:
        raise HTTPException(503, "file_unavailable") from None
    try:
        audit(db, request, user.id, "FILE_DOWNLOADED", "document", doc_id, {"version_id": version_id})
        db.commit()
    except Exception:
        file.close()
        raise

    def chunks():
        try:
            while chunk := file.read(64 * 1024):
                yield chunk
        finally:
            file.close()

    return StreamingResponse(
        chunks(),
        media_type=version.mime_type,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(version.original_filename),
            "Content-Length": str(version.size),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{doc_id}/comments", response_model=list[CommentOut])
def comments(doc_id: str, db: Db, user: Actor) -> list[dict]:
    get_document(db, user, doc_id)
    return [
        {"id": c.id, "author_id": c.author_id, "body": c.body, "created_at": c.created_at}
        for c in db.scalars(
            select(Comment).where(Comment.document_id == doc_id).order_by(Comment.created_at).limit(500)
        )
    ]


@router.post("/{doc_id}/comments", status_code=201, response_model=CommentOut)
def comment(doc_id: str, body: CommentCreate, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require(user, "comment")
    if doc.status == "ARCHIVED" or doc.deleted_at is not None:
        raise HTTPException(409, "document_not_editable")
    c = Comment(document_id=doc_id, author_id=user.id, body=body.body)
    db.add(c)
    db.flush()
    audit(db, request, user.id, "COMMENT_ADDED", "document", doc_id, {"comment_id": c.id})
    db.commit()
    return {"id": c.id, "author_id": c.author_id, "body": c.body, "created_at": c.created_at}


@router.get("/{doc_id}/activity")
def activity(doc_id: str, db: Db, user: Actor) -> list[dict]:
    get_document(db, user, doc_id)
    return [
        {
            "id": a.id,
            "action": a.action,
            "actor_id": a.actor_id,
            "created_at": a.created_at,
            "safe_metadata": a.safe_metadata,
        }
        for a in db.scalars(
            select(AuditEvent)
            .where(AuditEvent.target_type == "document", AuditEvent.target_id == doc_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(200)
        )
    ]
