import hashlib
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from fastapi import HTTPException, UploadFile

from app.config import settings


@dataclass
class StoredFile:
    key: str
    name: str
    mime: str
    size: int
    sha256: str


class Storage(Protocol):
    def save(self, upload: UploadFile) -> StoredFile: ...

    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise ValueError("invalid_storage_key")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("invalid_storage_key")
        return path

    def open(self, key: str) -> BinaryIO:
        return self.path(key).open("rb")

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def save(self, upload: UploadFile) -> StoredFile:
        name = unicodedata.normalize("NFKC", (upload.filename or "").replace("\\", "/").split("/")[-1])
        name = "".join(c for c in name if unicodedata.category(c)[0] != "C" and c not in "/\\").strip(" .")
        if not name or len(name) > 200:
            raise HTTPException(422, "invalid_filename")
        ext = Path(name).suffix.lower()
        allowed = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        if ext not in allowed:
            raise HTTPException(422, "unsupported_file")
        if upload.content_type not in {allowed[ext], "application/octet-stream"}:
            raise HTTPException(422, "invalid_file_type")
        key, size, sha = uuid.uuid4().hex, 0, hashlib.sha256()
        try:
            with self.path(key).open("xb") as out:
                while chunk := upload.file.read(64 * 1024):
                    size += len(chunk)
                    if size > settings().max_upload_bytes:
                        raise HTTPException(413, "file_too_large")
                    sha.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise HTTPException(422, "empty_file")
            self.validate(self.path(key), ext)
        except Exception:
            self.delete(key)
            raise
        return StoredFile(key, name, allowed[ext], size, sha.hexdigest())

    @staticmethod
    def validate(path: Path, ext: str) -> None:
        try:
            if ext == ".pdf":
                with path.open("rb") as file:
                    if not file.read(8).startswith(b"%PDF-"):
                        raise ValueError("pdf signature")
            elif ext == ".txt":
                raw = path.read_bytes()
                raw.decode("utf-8")
                if b"\x00" in raw:
                    raise ValueError("binary text")
            else:
                with zipfile.ZipFile(path) as archive:
                    infos = archive.infolist()
                    names = {item.filename for item in infos}
                    if not {"[Content_Types].xml", "word/document.xml"} <= names:
                        raise ValueError("not docx")
                    if len(infos) > 2000 or sum(i.file_size for i in infos) > 100 * 1024 * 1024:
                        raise ValueError("zip limits")
                    if any(
                        i.flag_bits & 1
                        or ".." in Path(i.filename).parts
                        or i.filename.startswith(("/", "\\"))
                        or "vbaProject" in i.filename
                        for i in infos
                    ):
                        raise ValueError("unsafe archive")
                    for item in ("[Content_Types].xml", "word/document.xml"):
                        if archive.getinfo(item).file_size > 5 * 1024 * 1024:
                            raise ValueError("xml too large")
                        content = archive.read(item)
                        if b"<!ENTITY" in content.upper() or b"<!DOCTYPE" in content.upper():
                            raise ValueError("unsafe xml")
                    if b"macroEnabled" in archive.read("[Content_Types].xml"):
                        raise ValueError("macro document")
        except (ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError, KeyError):
            raise HTTPException(422, "invalid_file_content") from None


def storage() -> LocalStorage:
    return LocalStorage(settings().storage_root)
