"""Notifications, overdue escalation and the email outbox against the disposable nexora_test DB."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from test_acl_contracts import setup_flow, uploaded
from test_api import client, create
from test_api import database as database  # noqa: F401

from app import notification_dispatch, workflow_escalation
from app.config import settings
from app.models import Approval, AuditEvent, Notification, WorkflowInstance


def kinds(c, instance_id, database):
    with database() as db:
        user = c.get("/api/v1/auth/me").json()["user"]["id"]
        return sorted(db.scalars(select(Notification.kind).where(
            Notification.recipient_id == user, Notification.instance_id == instance_id)))


def instance_of(wf):
    return wf.split("/")[4]


def decide(c, wf, action, comment="Reason"):
    response = c.post(wf, json={"action": action, "comment": comment, "idempotency_key": str(uuid4())})
    assert response.status_code == 200, response.text
    return response


def test_assignment_advance_and_outcome_notify_the_right_people(database):
    owner, base, _, _, wf = setup_flow()
    instance = instance_of(wf)
    legal, stranger = client("legal"), client("stranger")
    assert kinds(legal, instance, database) == ["TASK_ASSIGNED"]
    assert kinds(owner, instance, database) == []  # the actor is never notified about their own action
    assert kinds(stranger, instance, database) == []  # later stages are notified when they open

    task = next(n for n in legal.get("/api/v1/notifications").json()["items"] if n["kind"] == "TASK_ASSIGNED")
    assert task["href"].startswith("/approvals/") and task["href"].endswith("/review")
    assert task["document"]["title"] == "Test document"  # the active assignee may read the card
    assert task["actor_name"] == "owner"
    assert legal.get("/api/v1/notifications/summary").json()["unread"] >= 1

    decide(legal, wf, "approve", "")
    assert kinds(stranger, instance, database) == ["TASK_ASSIGNED"]
    decide(stranger, wf, "reject")
    assert kinds(owner, instance, database) == ["WORKFLOW_REJECTED"]
    outcome = next(n for n in owner.get("/api/v1/notifications").json()["items"] if n["kind"] == "WORKFLOW_REJECTED")
    assert outcome["href"] == "/documents/" + base.rsplit("/", 1)[1] and outcome["actor_name"] == "stranger"


def test_parallel_rejection_withdraws_other_open_tasks(database):
    owner, _, _, _, wf = setup_flow(parallel=True)
    instance = instance_of(wf)
    legal, manager = client("legal"), client("manager")
    decide(legal, wf, "revision")
    assert kinds(manager, instance, database) == ["TASK_ASSIGNED", "TASK_CANCELLED"]
    assert kinds(owner, instance, database) == ["WORKFLOW_RETURNED"]
    assert kinds(legal, instance, database) == ["TASK_ASSIGNED"]


def test_owner_cancel_notifies_open_assignees_only(database):
    owner, _, _, _, wf = setup_flow()
    instance = instance_of(wf)
    decide(owner, wf, "cancel")
    assert kinds(client("legal"), instance, database) == ["TASK_ASSIGNED", "TASK_CANCELLED"]
    assert kinds(client("stranger"), instance, database) == []
    assert kinds(owner, instance, database) == []


def test_read_state_is_private_to_the_recipient(database):
    _, _, _, _, wf = setup_flow()
    legal, stranger = client("legal"), client("stranger")
    note = legal.get("/api/v1/notifications?unread=true").json()["items"][0]
    assert stranger.post(f"/api/v1/notifications/{note['id']}/read").status_code == 404
    assert legal.post(f"/api/v1/notifications/{note['id']}/read").status_code == 204
    assert legal.post(f"/api/v1/notifications/{note['id']}/read").status_code == 204  # idempotent
    assert all(n["id"] != note["id"] for n in legal.get("/api/v1/notifications?unread=true").json()["items"])
    assert legal.post("/api/v1/notifications/read-all").status_code == 204
    assert legal.get("/api/v1/notifications/summary").json() == {"unread": 0}
    # CSRF still applies to read-state changes.
    del legal.headers["x-csrf-token"]
    assert legal.post("/api/v1/notifications/read-all").status_code == 403


@pytest.fixture
def runtime_sessions(database, monkeypatch):
    factory = sessionmaker(create_engine(os.environ["NEXORA_TEST_DATABASE_URL"]), expire_on_commit=False)
    monkeypatch.setattr(workflow_escalation, "SessionLocal", factory)
    monkeypatch.setattr(notification_dispatch, "SessionLocal", factory)
    return factory


def overdue_flow(admin, owner, target):
    response = admin.post("/api/v1/workflow-templates", json={
        "code": "ESC_" + uuid4().hex[:10].upper(), "name_ru": "Эскалация", "name_en": "Escalation",
        "stages": [{"name_ru": "Этап", "name_en": "Stage", "selector": "user", "targets": [target], "due_hours": 1}],
    })
    assert response.status_code == 201, response.text
    base = "/api/v1/documents/" + create(owner)["id"]
    uploaded(owner, base)
    started = owner.post(base + "/workflows", json={
        "template_id": response.json()["id"], "expected_revision": owner.get(base).json()["revision"],
        "idempotency_key": str(uuid4()),
    })
    assert started.status_code == 201, started.text
    return started.json()["id"]


def test_overdue_tasks_escalate_once_without_leaking_the_document(database, runtime_sessions):
    admin, owner, manager = client("admin"), client(), client("manager")
    instance = overdue_flow(admin, owner, "admin")  # assignee in IT; IT has a manager
    with database.begin() as db:
        db.execute(update(Approval).where(Approval.instance_id == instance)
                   .values(due_at=datetime.now(UTC) - timedelta(hours=2)))

    dry = workflow_escalation.escalate()
    assert dry["dry_run"] is True and dry["planned"] >= 1
    with database() as db:
        assert db.scalar(select(Approval.escalated_at).where(Approval.instance_id == instance)) is None

    assert workflow_escalation.escalate(apply=True)["escalated"] >= 1
    assert kinds(admin, instance, database) == ["TASK_ASSIGNED", "TASK_OVERDUE"]
    assert kinds(owner, instance, database) == ["WORKFLOW_OVERDUE"]
    assert kinds(manager, instance, database) == ["TASK_ESCALATED"]
    escalated = next(n for n in manager.get("/api/v1/notifications").json()["items"]
                     if n["kind"] == "TASK_ESCALATED")
    # The manager is told who is late and when it was due, never what the document is.
    assert escalated["document"] is None and escalated["href"] is None
    assert escalated["data"]["assignee_name"] == "admin" and escalated["data"]["due_at"]

    second = workflow_escalation.escalate(apply=True)
    assert kinds(manager, instance, database) == ["TASK_ESCALATED"]
    assert second["planned"] == 0 or second["escalated"] == second["planned"]
    with database() as db:
        assert db.query(AuditEvent).filter(AuditEvent.action == "WORKFLOW_ESCALATED",
                                           AuditEvent.safe_metadata["instance_id"].as_string() == instance).count() == 1


def test_escalation_falls_back_to_admins_and_skips_finished_workflows(database, runtime_sessions):
    admin, owner = client("admin"), client()
    instance = overdue_flow(admin, owner, "legal")  # the legal department has no manager
    with database.begin() as db:
        db.execute(update(Approval).where(Approval.instance_id == instance)
                   .values(due_at=datetime.now(UTC) - timedelta(hours=2)))
    workflow_escalation.escalate(apply=True)
    assert kinds(admin, instance, database) == ["TASK_ESCALATED"]

    finished = overdue_flow(admin, owner, "legal")
    with database.begin() as db:
        db.execute(update(Approval).where(Approval.instance_id == finished)
                   .values(due_at=datetime.now(UTC) - timedelta(hours=2)))
    owner.post(f"/api/v1/workflows/{finished}/decisions",
               json={"action": "cancel", "comment": "Stop", "idempotency_key": str(uuid4())})
    workflow_escalation.escalate(apply=True)
    with database() as db:
        assert db.scalar(select(WorkflowInstance.status).where(WorkflowInstance.id == finished)) == "CANCELLED"
        assert db.scalar(select(Approval.escalated_at).where(Approval.instance_id == finished)) is None


def test_email_outbox_sends_generic_messages_once(database, runtime_sessions, monkeypatch):
    sent = []

    class FakeSmtp:
        def send_message(self, mail):
            sent.append(mail)

        def quit(self):
            pass

    monkeypatch.setattr(settings(), "smtp_host", "smtp.test")
    monkeypatch.setattr(settings(), "smtp_from", "nexora@test.local")
    monkeypatch.setattr(notification_dispatch, "connect", lambda: FakeSmtp())
    _, _, _, _, wf = setup_flow()
    with database() as db:
        row = db.scalar(select(Notification).where(Notification.instance_id == instance_of(wf)))
        assert row is not None and row.email_status == "PENDING"

    assert notification_dispatch.dispatch()["dry_run"] is True and not sent
    result = notification_dispatch.dispatch(apply=True)
    assert result["sent"] >= 1
    mail = next(m for m in sent if m["To"] == "legal@test.local")
    body = mail.get_content()
    assert "/notifications" in body and "Test document" not in body and "Test document" not in mail["Subject"]
    with database() as db:
        assert db.get(Notification, row.id).email_status == "SENT"
    count = len(sent)
    notification_dispatch.dispatch(apply=True)
    assert len(sent) == count


def test_email_is_off_without_smtp_host(database):
    _, _, _, _, wf = setup_flow()
    with database() as db:
        assert db.scalar(select(Notification.email_status).where(
            Notification.instance_id == instance_of(wf))) == "NONE"
    assert notification_dispatch.dispatch(apply=True)["disabled"] is True
