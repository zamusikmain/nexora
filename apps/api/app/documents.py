import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.audit import audit
from app.auth import Actor, Db
from app.config import settings
from app.custom_fields import validate_metadata
from app.models import (
    AccessGrant,
    Approval,
    AuditEvent,
    Comment,
    Document,
    DocumentType,
    DocumentVersion,
    Favorite,
    FileScan,
    User,
    WorkflowInstance,
    number_sequence,
    uid,
)
from app.policy import (
    can_read,
    grant_conditions,
    require,
    require_write,
    resource_visibility,
    visibility,
    visible_field,
)
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


def get_document(db: Db, user: Actor, doc_id: str, lock: bool = False,
                 action: str = "card", version_id: str | None = None) -> Document:
    query = select(Document).where(Document.id == doc_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    doc = db.scalar(query)
    if not doc or not can_read(db, user, doc, action, version_id):
        raise HTTPException(404, "not_found")
    return doc


def version_card_snapshot(doc: Document, version_id: str, changed_at: datetime) -> dict:
    return jsonable_encoder({**document_data(doc), "current_version_id": version_id,
                            "revision": doc.revision + 1, "updated_at": changed_at})


def active_review(db: Db, user: Actor, doc: Document) -> tuple[Approval, WorkflowInstance] | None:
    row = db.execute(select(Approval, WorkflowInstance).join(WorkflowInstance).where(
        WorkflowInstance.document_id == doc.id, WorkflowInstance.status == "RUNNING",
        Approval.user_id == user.id, Approval.status == "PENDING", Approval.stage == WorkflowInstance.stage,
    )).first()
    return (row[0], row[1]) if row and can_read(db, user, doc) else None


def document_projection(db: Db, user: Actor, doc: Document) -> dict:
    owner = doc.owner_id == user.id
    result = document_data(doc)
    if not owner:
        review = active_review(db, user, doc)
        if review:
            snapshot = review[1].metadata_snapshot
            # Legacy snapshots never borrow mutable present-day fields.
            result = snapshot.get("card") or {
                "id": doc.id, "number": "", "title": snapshot["title"], "type_id": "",
                "owner_id": "", "department_id": None, "status": "IN_APPROVAL",
                "business_metadata": snapshot["metadata"], "confidentiality": doc.confidentiality,
                "revision": snapshot["revision"], "current_version_id": review[1].document_version_id,
                "folder_id": None, "deleted_at": None, "created_at": review[1].created_at,
                "updated_at": review[1].created_at,
            }
            result = {**result, "status": "IN_APPROVAL", "current_version_id": review[1].document_version_id}
        else:
            grant = db.scalar(select(AccessGrant).join(Document, Document.id == AccessGrant.document_id).where(
                Document.id == doc.id, grant_conditions(user, doc.current_version_id, "card"),
            ).order_by(AccessGrant.requested_at.desc(), AccessGrant.id).limit(1))
            if grant and grant.snapshot:
                result = dict(grant.snapshot)
        result = {**result, "folder_id": None, "confidentiality": doc.confidentiality}
    capabilities = {"write": owner and doc.deleted_at is None and doc.status in {"DRAFT", "REVISION_REQUIRED"},
                    "workflow": owner, "share": owner and doc.deleted_at is None,
                    "versions": True, "comments": owner or active_review(db, user, doc) is not None,
                    "activity": can_read(db, user, doc, "history")}
    capabilities["compare"] = can_read(db, user, doc, "compare")
    capabilities["comments"] = capabilities["comments"] or can_read(db, user, doc, "comments")
    return {**result, "capabilities": capabilities}


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
                visible_field(user, "title").ilike(f"%{escaped}%", escape="\\"),
                Document.number.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    for column, value in [
        (Document.status, status),
        (Document.type_id, type_id),
        (Document.department_id, department_id),
    ]:
        if value:
            conditions.append((visible_field(user, "status") if column is Document.status else column) == value)
    total = db.scalar(select(func.count()).select_from(Document).where(*conditions))
    docs = db.scalars(
        select(Document)
        .where(*conditions)
        .order_by(Document.updated_at.desc(), Document.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": [document_projection(db, user, d) for d in docs], "total": total, "page": page}


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
    return document_projection(db, user, get_document(db, user, doc_id))


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
    if doc.confidentiality == "RESTRICTED" and "confidentiality" in body.model_fields_set \
            and body.confidentiality != "RESTRICTED":
        raise HTTPException(403, "classification_change_forbidden")
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
    if doc.owner_id != user.id:
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
    if body.action == "submit" and doc.current_version_id:
        current = db.get(DocumentVersion, doc.current_version_id)
        assert current is not None
        require_scan(current, db)
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
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.document_id == doc_id, resource_visibility(user, "file", DocumentVersion.id))
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
    try:
        saved = store.save(file)
    except HTTPException as error:
        audit(db, request, user.id, "FILE_UPLOAD_BLOCKED", "document", doc.id, {"reason": error.detail})
        db.commit()
        raise
    try:
        last = (
            db.scalar(
                select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == doc.id)
            )
            or 0
        )
        version_id, changed_at = uid(), datetime.now(UTC)
        version = DocumentVersion(
            id=version_id,
            document_id=doc.id,
            version_number=last + 1,
            original_filename=saved.name,
            storage_key=saved.key,
            mime_type=saved.mime,
            size=saved.size,
            sha256=saved.sha256,
            created_by=user.id,
            change_note=change_note or None,
            metadata_snapshot=version_card_snapshot(doc, version_id, changed_at),
        )
        db.add(version)
        db.flush()
        if saved.scanned_by:
            db.add(FileScan(version_id=version.id, sha256=version.sha256, engine=saved.scanned_by))
        doc.current_version_id = version.id
        doc.revision += 1
        doc.updated_at = changed_at
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
    get_document(db, user, doc_id, action="file", version_id=version_id)
    version = db.scalar(
        select(DocumentVersion).where(DocumentVersion.id == version_id, DocumentVersion.document_id == doc_id)
    )
    if not version:
        raise HTTPException(404, "not_found")
    require_scan(version, db)
    try:
        file = storage().open(version.storage_key)
    except FileNotFoundError:
        raise HTTPException(503, "file_unavailable") from None
    try:
        checksum = hashlib.sha256()
        read_size = 0
        while chunk := file.read(64 * 1024):
            read_size += len(chunk)
            if read_size > version.size:
                raise HTTPException(503, "file_unavailable")
            checksum.update(chunk)
        if read_size != version.size or checksum.hexdigest() != version.sha256:
            raise HTTPException(503, "file_unavailable")
        file.seek(0)
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
    doc = get_document(db, user, doc_id)
    conditions = [Comment.document_id == doc_id]
    if doc.owner_id != user.id:
        review = active_review(db, user, doc)
        if review:
            conditions += [Comment.instance_id == review[1].id, Comment.stage == review[0].stage,
                           Comment.version_id == review[1].document_version_id]
        else:
            if not can_read(db, user, doc, "comments"):
                raise HTTPException(404, "not_found")
            conditions += [Comment.version_id == doc.current_version_id, Comment.instance_id.is_(None)]
    return [
        {"id": c.id, "author_id": c.author_id, "body": c.body, "created_at": c.created_at}
        for c in db.scalars(
            select(Comment).where(*conditions).order_by(Comment.created_at).limit(500)
        )
    ]


@router.post("/{doc_id}/comments", status_code=201, response_model=CommentOut)
def comment(doc_id: str, body: CommentCreate, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require(user, "comment")
    if doc.status == "ARCHIVED" or doc.deleted_at is not None:
        raise HTTPException(409, "document_not_editable")
    review = active_review(db, user, doc)
    if doc.owner_id != user.id and not review and not can_read(db, user, doc, "comments"):
        raise HTTPException(404, "not_found")
    # An owner's new reply during a running review belongs to its current stage.
    # Never relabel legacy comments or let a client choose a different stage.
    process = review[1] if review else db.scalar(select(WorkflowInstance).where(
        WorkflowInstance.document_id == doc.id, WorkflowInstance.status == "RUNNING",
    )) if doc.owner_id == user.id and doc.status == "IN_APPROVAL" else None
    c = Comment(document_id=doc_id, author_id=user.id, body=body.body,
                version_id=process.document_version_id if process else doc.current_version_id,
                instance_id=process.id if process else None, stage=process.stage if process else None)
    db.add(c)
    db.flush()
    audit(db, request, user.id, "COMMENT_ADDED", "document", doc_id,
          {"comment_id": c.id, "version_id": c.version_id})
    db.commit()
    return {"id": c.id, "author_id": c.author_id, "body": c.body, "created_at": c.created_at}


@router.get("/{doc_id}/activity")
def activity(doc_id: str, db: Db, user: Actor) -> list[dict]:
    doc = get_document(db, user, doc_id, action="history")
    conditions = [AuditEvent.target_type == "document", AuditEvent.target_id == doc_id]
    if doc.owner_id != user.id:
        conditions.append(AuditEvent.safe_metadata["version_id"].as_string() == doc.current_version_id)
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
            .where(*conditions)
            .order_by(AuditEvent.created_at.desc())
            .limit(200)
        )
    ]


def require_scan(version: DocumentVersion, db: Db) -> None:
    if settings().app_env == "production":
        record = db.get(FileScan, version.id)
        if record is None or record.sha256 != version.sha256 or record.engine != "clamav":
            raise HTTPException(503, "file_scan_required")
