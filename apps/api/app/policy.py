from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.models import Document, User

PERMISSIONS = {
    "USER": {"create", "comment"},
    "REVIEWER": {"create", "comment"},
    "APPROVER": {"create", "comment"},
    "LEGAL": {"create", "comment"},
    "MANAGER": {"create", "comment", "department_read"},
    "ADMIN": {"create", "comment", "all_read", "admin", "audit"},
}


def require(user: User, permission: str) -> None:
    if permission not in PERMISSIONS.get(user.role, set()):
        raise HTTPException(403, "forbidden")


def visibility(user: User) -> ColumnElement[bool]:
    if "all_read" in PERMISSIONS[user.role]:
        return Document.id.is_not(None)
    own = Document.owner_id == user.id
    if "department_read" in PERMISSIONS[user.role] and user.department_id:
        return or_(own, Document.department_id == user.department_id)
    return own


def can_read(user: User, doc: Document) -> bool:
    return (
        doc.owner_id == user.id
        or "all_read" in PERMISSIONS[user.role]
        or (
            "department_read" in PERMISSIONS[user.role]
            and user.department_id is not None
            and user.department_id == doc.department_id
        )
    )


def require_write(user: User, doc: Document) -> None:
    if doc.owner_id != user.id and "admin" not in PERMISSIONS[user.role]:
        raise HTTPException(403, "forbidden")
    if doc.deleted_at is not None:
        raise HTTPException(409, "document_in_trash")
    if doc.status not in {"DRAFT", "REVISION_REQUIRED"}:
        raise HTTPException(409, "document_not_editable")
