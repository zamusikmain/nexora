"""DMS operations preserve version and audit history."""

import difflib
import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.audit import audit
from app.auth import Actor, Db
from app.documents import document_data, get_document, require_scan, version_card_snapshot, version_data
from app.models import DocumentVersion, Favorite, FileScan, Folder, uid
from app.policy import assert_read, require_write
from app.schemas import Input
from app.storage import storage

router = APIRouter(tags=["dms"])


class FolderInput(Input):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = Field(default=None, max_length=36)


class Move(Input):
    folder_id: str | None = Field(default=None, max_length=36)
    expected_revision: int = Field(ge=1)


class Revision(Input):
    expected_revision: int = Field(ge=1)


def folder_data(folder: Folder) -> dict:
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id, "owner_id": folder.owner_id}


def get_folder(db: Db, user: Actor, folder_id: str) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None or folder.owner_id != user.id:
        raise HTTPException(404, "not_found")
    return folder


def check_revision(doc, expected):
    if doc.revision != expected:
        raise HTTPException(409, "stale_document")


def require_owner(user, doc):
    if user.id != doc.owner_id:
        raise HTTPException(403, "forbidden")


@router.get("/folders")
def folders(db: Db, user: Actor, parent_id: str | None = None) -> list[dict]:
    if parent_id:
        get_folder(db, user, parent_id)
    query = select(Folder).where(Folder.parent_id == parent_id).order_by(Folder.name, Folder.id).limit(200)
    query = query.where(Folder.owner_id == user.id)
    return [folder_data(f) for f in db.scalars(query)]


@router.get("/folders/{folder_id}/breadcrumbs")
def breadcrumbs(folder_id: str, db: Db, user: Actor) -> list[dict]:
    result = []
    current: str | None = folder_id
    while current:
        folder = get_folder(db, user, current)
        result.append(folder_data(folder))
        current = folder.parent_id
        if len(result) > 32:
            raise HTTPException(409, "folder_depth")
    return result[::-1]


@router.post("/folders", status_code=201)
def create_folder(body: FolderInput, request: Request, db: Db, user: Actor) -> dict:
    # Serialize all mutations of one owner's tree, including creation and moves.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:owner, 0))"), {"owner": user.id})
    if body.parent_id:
        parent = get_folder(db, user, body.parent_id)
        if parent.owner_id != user.id:
            raise HTTPException(403, "forbidden")
        if len(breadcrumbs(parent.id, db, user)) >= 32:
            raise HTTPException(409, "folder_depth")
    folder = Folder(name=body.name, parent_id=body.parent_id, owner_id=user.id)
    db.add(folder)
    db.flush()
    audit(db, request, user.id, "FOLDER_CREATED", "folder", folder.id)
    db.commit()
    return folder_data(folder)


@router.patch("/folders/{folder_id}")
def move_folder(folder_id: str, body: FolderInput, request: Request, db: Db, user: Actor) -> dict:
    folder = get_folder(db, user, folder_id)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:owner, 0))"), {"owner": folder.owner_id})
    db.refresh(folder)
    if body.parent_id:
        parent = get_folder(db, user, body.parent_id)
        if parent.owner_id != folder.owner_id:
            raise HTTPException(403, "forbidden")
        ancestors = breadcrumbs(parent.id, db, user)
        if any(f["id"] == folder_id for f in ancestors):
            raise HTTPException(409, "folder_cycle")
        # Enforce total depth, including the moved subtree, using a bounded CTE.
        depth = db.scalar(
            text("""WITH RECURSIVE children AS (
            SELECT id, 1 AS depth FROM folders WHERE id=:id
            UNION ALL SELECT f.id, c.depth+1 FROM folders f JOIN children c ON f.parent_id=c.id WHERE c.depth <= 32
            ) SELECT max(depth) FROM children"""),
            {"id": folder_id},
        )
        if len(ancestors) + depth > 32:
            raise HTTPException(409, "folder_depth")
    folder.name, folder.parent_id = body.name, body.parent_id
    audit(db, request, user.id, "FOLDER_UPDATED", "folder", folder.id, {"parent_id": body.parent_id})
    db.commit()
    return folder_data(folder)


@router.post("/documents/{doc_id}/move")
def move_document(doc_id: str, body: Move, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require_write(user, doc)
    check_revision(doc, body.expected_revision)
    if body.folder_id:
        folder = get_folder(db, user, body.folder_id)
        if folder.owner_id != doc.owner_id:
            raise HTTPException(403, "forbidden")
    doc.folder_id = body.folder_id
    doc.revision += 1
    audit(db, request, user.id, "DOCUMENT_MOVED", "document", doc.id, {"folder_id": body.folder_id})
    db.commit()
    return document_data(doc)


@router.put("/documents/{doc_id}/favorite", status_code=204)
def favorite(doc_id: str, db: Db, user: Actor):
    get_document(db, user, doc_id)
    db.execute(insert(Favorite).values(user_id=user.id, document_id=doc_id).on_conflict_do_nothing())
    db.commit()


@router.delete("/documents/{doc_id}/favorite", status_code=204)
def unfavorite(doc_id: str, db: Db, user: Actor):
    get_document(db, user, doc_id)
    row = db.get(Favorite, (user.id, doc_id))
    if row:
        db.delete(row)
    db.commit()


@router.post("/documents/{doc_id}/trash")
def trash(doc_id: str, body: Revision, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require_owner(user, doc)
    check_revision(doc, body.expected_revision)
    if doc.deleted_at is not None or doc.status not in {
        "DRAFT",
        "REVISION_REQUIRED",
        "CANCELLED",
        "REJECTED",
        "ARCHIVED",
    }:
        raise HTTPException(409, "invalid_transition")
    doc.deleted_at = datetime.now(UTC)
    doc.revision += 1
    audit(db, request, user.id, "DOCUMENT_TRASHED", "document", doc.id)
    db.commit()
    return document_data(doc)


@router.post("/documents/{doc_id}/restore")
def restore_document(doc_id: str, body: Revision, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require_owner(user, doc)
    check_revision(doc, body.expected_revision)
    if doc.deleted_at is None:
        raise HTTPException(409, "invalid_transition")
    doc.deleted_at = None
    doc.revision += 1
    audit(db, request, user.id, "DOCUMENT_RESTORED", "document", doc.id)
    db.commit()
    return document_data(doc)


@router.post("/documents/{doc_id}/versions/{version_id}/restore", status_code=201)
def restore_version(
    doc_id: str, version_id: str, body: Revision, request: Request, db: Db, user: Actor
) -> dict:
    doc = get_document(db, user, doc_id, lock=True)
    require_write(user, doc)
    check_revision(doc, body.expected_revision)
    source = db.scalar(
        select(DocumentVersion).where(DocumentVersion.id == version_id, DocumentVersion.document_id == doc_id)
    )
    if not source:
        raise HTTPException(404, "not_found")
    # Copy through the same validated storage interface. Old rows and bytes never change.
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    store = storage()
    try:
        with store.open(source.storage_key) as file:
            saved = store.save(
                UploadFile(
                    file,
                    filename=source.original_filename,
                    headers=Headers({"content-type": source.mime_type}),
                )
            )
    except FileNotFoundError:
        raise HTTPException(503, "file_unavailable") from None
    if saved.sha256 != source.sha256:
        store.delete(saved.key)
        raise HTTPException(503, "file_unavailable")
    from sqlalchemy import func

    last = (
        db.scalar(
            select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == doc_id)
        )
        or 0
    )
    version_id, changed_at = uid(), datetime.now(UTC)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number=last + 1,
        original_filename=saved.name,
        storage_key=saved.key,
        mime_type=saved.mime,
        size=saved.size,
        sha256=saved.sha256,
        created_by=user.id,
        change_note=None,
        metadata_snapshot=version_card_snapshot(doc, version_id, changed_at),
    )
    db.add(version)
    db.flush()
    if saved.scanned_by:
        db.add(FileScan(version_id=version.id, sha256=version.sha256, engine=saved.scanned_by))
    doc.current_version_id = version.id
    doc.revision += 1
    doc.updated_at = changed_at
    audit(
        db,
        request,
        user.id,
        "VERSION_RESTORED",
        "document",
        doc.id,
        {"source_version_id": source.id, "version_id": version.id},
    )
    db.commit()
    return version_data(version)


@router.get("/documents/{doc_id}/versions/{version_id}/diff/{other_id}")
def diff(doc_id: str, version_id: str, other_id: str, request: Request, db: Db, user: Actor) -> dict:
    doc = get_document(db, user, doc_id)
    versions = []
    for key in (version_id, other_id):
        assert_read(db, user, doc, "file", key)
        assert_read(db, user, doc, "compare", key)
        version = db.scalar(
            select(DocumentVersion).where(DocumentVersion.id == key, DocumentVersion.document_id == doc_id)
        )
        if not version:
            raise HTTPException(404, "not_found")
        if version.mime_type != "text/plain" or version.size > 256 * 1024:
            raise HTTPException(422, "diff_unsupported")
        require_scan(version, db)
        versions.append(version)
    contents = []
    try:
        for version in versions:
            with storage().open(version.storage_key) as file:
                raw = file.read(256 * 1024 + 1)
                if hashlib.sha256(raw).hexdigest() != version.sha256:
                    raise HTTPException(503, "file_unavailable")
                contents.append(raw.decode("utf-8").splitlines(keepends=True))
    except (FileNotFoundError, UnicodeError):
        raise HTTPException(503, "file_unavailable") from None
    # Bound CPU on adversarial text; never hand arbitrary binary files to parsers.
    if any(len(lines) > 2000 for lines in contents):
        raise HTTPException(422, "diff_unsupported")
    result = "".join(
        difflib.unified_diff(
            contents[0],
            contents[1],
            fromfile=str(versions[0].version_number),
            tofile=str(versions[1].version_number),
        )
    )
    audit(db, request, user.id, "VERSIONS_COMPARED", "document", doc_id, {"versions": [version_id, other_id]})
    db.commit()
    return {"diff": result}
