import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class DocumentMetadata(Input):
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)
    responsible_id: str | None = Field(default=None, max_length=36)
    confidentiality: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] = "INTERNAL"
    effective_date: date | None = None
    expiration_date: date | None = None

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, value):
        if any(not tag.strip() or len(tag) > 50 for tag in value) or len(set(value)) != len(value):
            raise ValueError("invalid_tags")
        return value

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_date and self.expiration_date and self.expiration_date < self.effective_date:
            raise ValueError("invalid_dates")
        return self


class DocumentCreate(DocumentMetadata):
    title: str = Field(min_length=1, max_length=240)
    type_id: str = Field(min_length=1, max_length=36)
    business_metadata: dict[str, Any] = Field(default_factory=dict)

    _bounded = field_validator("business_metadata")(bounded_metadata)


class DocumentUpdate(DocumentMetadata):
    expected_revision: int | None = Field(default=None, ge=1)
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


class DocumentOut(DocumentMetadata):
    folder_id: str | None
    deleted_at: datetime | None
    revision: int
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
