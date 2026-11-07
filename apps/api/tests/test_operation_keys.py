"""Signed, expiring retry keys (B2). Unit tests need no DB; integration uses nexora_test only."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from test_api import client
from test_api import database as database  # noqa: F401 -- guarded nexora_test fixture

from app import operation_key_cleanup
from app.config import settings
from app.models import Document, OperationKey
from app.operation_keys import issue, resolve

owner = SimpleNamespace(id="owner")
other = SimpleNamespace(id="stranger")


def error(call) -> tuple[int, str]:
    with pytest.raises(HTTPException) as caught:
        call()
    return caught.value.status_code, caught.value.detail


def test_signed_key_round_trip_and_tampering():
    token, expires = issue(owner)
    key, stored_expiry = resolve(token, owner)
    assert str(uuid.UUID(key)) == key and stored_expiry == expires.replace(microsecond=0)
    assert expires - datetime.now(UTC) > timedelta(days=29)
    prefix, payload, signature = token.split(".")
    forged = f"{prefix}.{payload}.{'A' * len(signature)}"
    assert error(lambda: resolve(forged, owner)) == (422, "invalid_idempotency_key")
    assert error(lambda: resolve(token, other)) == (422, "invalid_idempotency_key")
    assert error(lambda: resolve("nx1.garbage", owner)) == (422, "invalid_idempotency_key")
    assert error(lambda: resolve(None, owner)) == (422, "idempotency_key_required")


def test_expired_future_and_old_epoch_keys_never_execute(monkeypatch):
    old, _ = issue(owner, now=datetime.now(UTC) - timedelta(days=31))
    assert error(lambda: resolve(old, owner)) == (409, "operation_expired")
    future, _ = issue(owner, now=datetime.now(UTC) + timedelta(hours=1))
    assert error(lambda: resolve(future, owner)) == (422, "invalid_idempotency_key")
    current, _ = issue(owner)
    monkeypatch.setattr(settings(), "operation_key_epoch", settings().operation_key_epoch + 1)
    assert error(lambda: resolve(current, owner)) == (409, "operation_expired")


def test_legacy_uuid_keys_only_until_the_cutoff(monkeypatch):
    legacy = str(uuid.uuid4())
    assert resolve(legacy, owner) == (legacy, None)
    monkeypatch.setattr(settings(), "legacy_operation_keys_until", datetime.now(UTC) - timedelta(seconds=1))
    assert error(lambda: resolve(legacy, owner)) == (409, "operation_legacy_rejected")
    token, _ = issue(owner)
    assert resolve(token, owner)[0]  # signed keys keep working after the cutoff


def test_signed_key_replays_once_and_expired_key_is_refused(database):
    c = client()
    token = c.post("/api/v1/operation-keys").json()["key"]
    body = {"title": "Signed key " + uuid.uuid4().hex, "type_id": "type"}
    first = c.post("/api/v1/documents", json=body, headers={"Idempotency-Key": token})
    again = c.post("/api/v1/documents", json=body, headers={"Idempotency-Key": token})
    assert first.status_code == 201 and again.json()["id"] == first.json()["id"]
    with database() as db:
        assert list(db.scalars(select(Document.id).where(Document.title == body["title"]))) == [first.json()["id"]]
        row = db.scalar(select(OperationKey).where(OperationKey.actor_id == "owner").order_by(
            OperationKey.created_at.desc()).limit(1))
        assert row.expires_at is not None and row.expires_at > datetime.now(UTC) + timedelta(days=29)
        assert "." not in row.key  # only the inner operation id is stored
    # Another user cannot use someone else's key.
    assert client("stranger").post("/api/v1/documents", json=body, headers={"Idempotency-Key": token}).status_code == 422
    expired, _ = issue(owner, now=datetime.now(UTC) - timedelta(days=40))
    late = c.post("/api/v1/documents", json={**body, "title": "Must not exist"}, headers={"Idempotency-Key": expired})
    assert late.status_code == 409 and late.json()["error"] == "operation_expired"
    with database() as db:
        assert db.scalar(select(Document.id).where(Document.title == "Must not exist")) is None


def test_purge_removes_only_long_expired_signed_keys(database, monkeypatch):
    monkeypatch.setattr(operation_key_cleanup, "SessionLocal", database)
    now = datetime.now(UTC)
    rows = {"old": now - timedelta(days=3), "fresh": now - timedelta(hours=2), "legacy": None}
    keys = {name: str(uuid.uuid4()) for name in rows}
    with database.begin() as db:
        for name, expires in rows.items():
            db.add(OperationKey(actor_id="owner", key=keys[name], fingerprint="f" * 64, response={},
                                expires_at=expires))
    dry = operation_key_cleanup.purge(now=now)
    assert dry["dry_run"] and dry["planned"] >= 1 and dry["deleted"] is None
    result = operation_key_cleanup.purge(apply=True, now=now)
    assert result["deleted"] >= 1
    with database() as db:
        left = set(db.scalars(select(OperationKey.key).where(OperationKey.key.in_(keys.values()))))
    assert left == {keys["fresh"], keys["legacy"]}
    # The trigger refuses deleting legacy or recently expired keys for every role.
    for name in ("legacy", "fresh"):
        with pytest.raises(DBAPIError), database.begin() as db:
            db.execute(delete(OperationKey).where(OperationKey.key == keys[name]))
    with database.begin() as db:
        assert db.execute(text("SELECT count(*) FROM operation_keys WHERE key = :k"), {"k": keys["fresh"]}).scalar() == 1
