import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


def bounded_metadata(value: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(value, allow_nan=False).encode()) > 16384:
        raise ValueError("metadata_too_large")
    return value


class DocumentCreate(Input):
    title: str = Field(min_length=1, max_length=240)
    type_id: str = Field(min_length=1, max_length=36)
    business_metadata: dict[str, Any] = Field(default_factory=dict)

    _bounded = field_validator("business_metadata")(bounded_metadata)


class DocumentUpdate(Input):
    title: str = Field(min_length=1, max_length=240)
    business_metadata: dict[str, Any] = Field(default_factory=dict)
    _bounded = field_validator("business_metadata")(bounded_metadata)


class Transition(Input):
    action: str = Field(pattern="^(submit|cancel|archive)$")


class CommentCreate(Input):
    body: str = Field(min_length=1, max_length=4000)


class UserUpdate(Input):
    role: str = Field(pattern="^(USER|REVIEWER|APPROVER|LEGAL|MANAGER|ADMIN)$")
    status: str = Field(pattern="^(ACTIVE|BLOCKED|DISABLED)$")
    department_id: str | None = Field(default=None, max_length=36)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    status: str
    department_id: str | None


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class DocumentOut(BaseModel):
    id: str
    number: str
    title: str
    type_id: str
    owner_id: str
    department_id: str | None
    status: str
    business_metadata: dict[str, Any]
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int


class VersionOut(BaseModel):
    id: str
    document_id: str
    version_number: int
    original_filename: str
    mime_type: str
    size: int
    sha256: str
    created_at: datetime
    created_by: str
    change_note: str | None


class CommentOut(BaseModel):
    id: str
    author_id: str
    body: str
    created_at: datetime
