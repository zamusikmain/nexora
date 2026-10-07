"""Bounded declarative field validation; no executable expressions or regex."""

import math
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from app.models import Department, User
from app.schemas import Input, bounded_metadata

KINDS = Literal[
    "text",
    "textarea",
    "number",
    "date",
    "datetime",
    "boolean",
    "select",
    "multi-select",
    "user",
    "department",
    "URL",
]


class CustomField(Input):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name_ru: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)
    kind: KINDS
    required: bool = False
    enabled: bool = True
    default: Any = None
    options: list[str] = Field(default_factory=list, max_length=100)
    order: int = Field(default=0, ge=0, le=1000)
    minimum: float | None = None
    maximum: float | None = None
    max_length: int = Field(default=2000, ge=1, le=4000)

    @model_validator(mode="after")
    def valid_definition(self):
        if self.kind in {"select", "multi-select"} and not self.options:
            raise ValueError("options_required")
        if len(self.options) != len(set(self.options)) or any(
            not x.strip() or len(x) > 200 for x in self.options
        ):
            raise ValueError("invalid_options")
        if self.minimum is not None and not math.isfinite(self.minimum):
            raise ValueError("invalid_minimum")
        if self.maximum is not None and not math.isfinite(self.maximum):
            raise ValueError("invalid_maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("invalid_range")
        if self.default is not None:
            validate_value(self, self.default, None)
        return self


class TypeInput(Input):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,39}$")
    name_ru: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)
    fields: list[CustomField] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_fields(self):
        if len({f.key for f in self.fields}) != len(self.fields):
            raise ValueError("duplicate_fields")
        return self


def validate_value(field: CustomField, value: Any, db: Session | None) -> None:
    kind = field.kind
    valid = True
    if kind in {"text", "textarea", "date", "datetime", "user", "department", "URL", "select"}:
        valid = isinstance(value, str) and 0 < len(value) <= field.max_length
    elif kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "number":
        valid = type(value) in {int, float} and math.isfinite(value)
        if valid and field.minimum is not None:
            valid = value >= field.minimum
        if valid and field.maximum is not None:
            valid = value <= field.maximum
    elif kind == "multi-select":
        valid = (
            isinstance(value, list)
            and len(value) <= len(field.options)
            and all(isinstance(v, str) and v in field.options for v in value)
            and len(set(value)) == len(value)
        )
    if not valid:
        raise ValueError("invalid_custom_field")
    if kind == "select" and value not in field.options:
        raise ValueError("invalid_custom_field")
    if kind == "date":
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("invalid_custom_field")
    if kind == "datetime" and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("invalid_custom_field")
    if kind == "URL":
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("invalid_custom_field")
    if db is not None and kind in {"user", "department"}:
        row = db.get(User if kind == "user" else Department, value)
        if row is None or (isinstance(row, User) and row.status != "ACTIVE"):
            raise ValueError("invalid_custom_field")


def validate_metadata(schema: dict, values: dict, db: Session) -> dict:
    # Empty historical schemas remain open JSON for Iteration 1 compatibility.
    if not schema.get("fields"):
        return values
    fields = [CustomField.model_validate(f) for f in schema["fields"]]
    if set(values) - {f.key for f in fields}:
        raise HTTPException(422, "invalid_custom_field")
    result = dict(values)
    try:
        for field in fields:
            if not field.enabled:
                # Preserve historical values without revalidating disabled definitions.
                continue
            if field.key not in result and field.default is not None:
                result[field.key] = field.default
            value = result.get(field.key)
            if value is None or value == "" or value == []:
                if field.required:
                    raise ValueError("required_custom_field")
                continue
            validate_value(field, value, db)
        return bounded_metadata(result)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(422, "invalid_custom_field") from None
