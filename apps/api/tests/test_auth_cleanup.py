import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

import app.auth_cleanup as auth_cleanup
from app.config import settings
from app.models import AuditEvent, AuthSession, LoginThrottle, User


@pytest.fixture
def factory(monkeypatch):
    url = os.getenv("NEXORA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set NEXORA_TEST_DATABASE_URL to a disposable PostgreSQL database named nexora_test")
    engine = create_engine(url)
    if engine.url.database != "nexora_test":
        pytest.fail("Integration tests only accept database named nexora_test")
    previous = settings().database_url
    settings().database_url = os.getenv("NEXORA_TEST_MIGRATIONS_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings().database_url = previous
    admin = sessionmaker(create_engine(os.getenv("NEXORA_TEST_ADMIN_URL", url)), expire_on_commit=False)
    monkeypatch.setattr(auth_cleanup, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    with admin.begin() as db:
        db.execute(delete(AuthSession).where(AuthSession.user_id == "cleanup-user"))
        db.execute(delete(LoginThrottle).where(LoginThrottle.id.like("cleanup-%")))
        db.execute(delete(User).where(User.id == "cleanup-user"))
        db.add(User(id="cleanup-user", email="cleanup@test.local", display_name="cleanup", role="USER",
                    status="ACTIVE", password_hash="x"))
    yield admin
    with admin.begin() as db:
        db.execute(delete(AuthSession).where(AuthSession.user_id == "cleanup-user"))
        db.execute(delete(LoginThrottle).where(LoginThrottle.id.like("cleanup-%")))
        db.execute(delete(User).where(User.id == "cleanup-user"))


def test_purge_removes_only_stale_rows_and_dry_run_changes_nothing(factory):
    now = datetime.now(UTC)
    with factory.begin() as db:
        for sid, expires in [("cleanup-old", now - timedelta(days=3)), ("cleanup-recent", now - timedelta(hours=2)),
                             ("cleanup-live", now + timedelta(hours=5))]:
            db.add(AuthSession(id=sid, user_id="cleanup-user", csrf_token="c", expires_at=expires))
        for tid, start in [("cleanup-stale", now - timedelta(days=2)), ("cleanup-active", now - timedelta(minutes=5))]:
            db.add(LoginThrottle(id=tid, failures=20, window_start=start))

    dry = auth_cleanup.purge(now=now)
    assert dry["dry_run"] is True and dry["deleted"] is None
    assert dry["planned"]["sessions"] >= 1 and dry["planned"]["throttles"] >= 1
    with factory() as db:
        assert db.get(AuthSession, "cleanup-old") is not None
        assert db.get(LoginThrottle, "cleanup-stale") is not None

    result = auth_cleanup.purge(apply=True, now=now)
    assert result["deleted"]["sessions"] >= 1 and result["deleted"]["throttles"] >= 1
    with factory() as db:
        remaining_sessions = set(db.scalars(select(AuthSession.id).where(AuthSession.user_id == "cleanup-user")))
        remaining_throttles = set(db.scalars(select(LoginThrottle.id).where(LoginThrottle.id.like("cleanup-%"))))
        # Expired within the grace period and live sessions stay; an active throttle window is never reset.
        assert remaining_sessions == {"cleanup-recent", "cleanup-live"}
        assert remaining_throttles == {"cleanup-active"}
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "AUTH_CLEANUP_COMPLETED")
                          .order_by(AuditEvent.created_at.desc()).limit(1))
        assert event is not None and event.safe_metadata["grace_hours"] == 24


def test_grace_must_be_positive():
    with pytest.raises(ValueError):
        auth_cleanup.purge(grace_hours=0)
