from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.auth import digest, password_hasher
from app.models import Document, User
from app.policy import can_read, require, require_write
from app.schemas import DocumentCreate, DocumentUpdate, Transition
from app.storage import LocalStorage


def user(role="USER", department="it", identity="owner"):
    return User(id=identity, role=role, department_id=department, status="ACTIVE")


def document(status="DRAFT"):
    return Document(id="document", owner_id="owner", department_id="it", status=status)


@pytest.mark.parametrize("role", ["USER", "REVIEWER", "APPROVER", "LEGAL"])
def test_roles_do_not_read_other_documents(role):
    assert not can_read(user(role, identity="outsider"), document())
    assert can_read(user(role), document())


def test_manager_scope_and_admin():
    assert can_read(user("MANAGER", identity="manager"), document())
    assert not can_read(user("MANAGER", "legal", "manager"), document())
    assert can_read(user("ADMIN", "legal", "admin"), document())
    with pytest.raises(HTTPException):
        require(user(), "audit")
    with pytest.raises(HTTPException):
        require_write(user("MANAGER", identity="manager"), document())
    with pytest.raises(HTTPException):
        require_write(user(), document("SUBMITTED"))


def test_status_and_identity_cannot_be_smuggled():
    for extra in ({"status": "APPROVED"}, {"owner_id": "admin"}, {"department_id": "legal"}):
        with pytest.raises(ValidationError):
            DocumentCreate(title="test", type_id="type", **extra)
    with pytest.raises(ValidationError):
        DocumentUpdate(title="test", status="APPROVED")
    with pytest.raises(ValidationError):
        Transition(action="approve")
    with pytest.raises(ValidationError):
        DocumentCreate(title=" ", type_id="type")


def test_metadata_size():
    with pytest.raises(ValidationError):
        DocumentCreate(title="test", type_id="type", business_metadata={"large": "x" * 17000})


def test_argon_and_digest():
    hashed = password_hasher.hash("test-password")
    assert hashed.startswith("$argon2id$")
    assert password_hasher.verify(hashed, "test-password")
    assert digest("token") != "token"


def upload(name, content, mime):
    return UploadFile(filename=name, file=BytesIO(content), headers=Headers({"content-type": mime}))


def test_private_storage_validation(tmp_path):
    store = LocalStorage(tmp_path)
    saved = store.save(upload("../../example.txt", "Пример".encode(), "text/plain"))
    assert saved.name == "example.txt"
    assert len(saved.sha256) == 64
    with store.open(saved.key) as file:
        assert file.read() == "Пример".encode()
    with pytest.raises(ValueError):
        store.path("../../outside")
    for name, content, mime in [
        ("fake.pdf", b"not a PDF", "application/pdf"),
        ("binary.txt", b"\x00", "text/plain"),
        ("empty.txt", b"", "text/plain"),
        ("bad.exe", b"MZ", "application/octet-stream"),
        ("bad.docx", b"PKnotzip", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ]:
        with pytest.raises(HTTPException):
            store.save(upload(name, content, mime))
    assert len(list(Path(tmp_path).iterdir())) == 1


def test_upload_size_limit(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "max_upload_bytes", 8)
    with pytest.raises(HTTPException) as error:
        LocalStorage(tmp_path).save(upload("big.txt", b"123456789", "text/plain"))
    assert error.value.status_code == 413
    assert not list(tmp_path.iterdir())
