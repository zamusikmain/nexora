"""Operator-run email delivery of pending notifications (outbox). Dry-run by default.

Emails never carry document numbers, titles or comments: mail leaves the trust boundary, so the
message only says that something is waiting and links to the notification page, where the ACL
applies. Delivery is at least once: a crash between sending and committing can repeat one email.
Rows are claimed with SKIP LOCKED, so several dispatchers never send the same row concurrently.
"""

import argparse
import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import AuditEvent, Notification, User

BATCH = 100
MAX_ATTEMPTS = 5


def message(recipient: str) -> EmailMessage:
    link = settings().web_origin + "/notifications"
    mail = EmailMessage()
    mail["From"] = settings().smtp_from
    mail["To"] = recipient
    mail["Subject"] = "NEXORA: новое уведомление / new notification"
    mail.set_content(
        "В NEXORA есть новое уведомление. Откройте: " + link + "\n\n"
        "You have a new notification in NEXORA. Open: " + link + "\n"
    )
    return mail


def connect() -> smtplib.SMTP:
    config = settings()
    server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
    if config.smtp_starttls:
        server.starttls()
    if config.smtp_username:
        server.login(config.smtp_username, config.smtp_password)
    return server


def dispatch(*, apply: bool = False) -> dict:
    if not settings().smtp_host:
        return {"dry_run": not apply, "disabled": True, "planned": 0, "sent": 0, "failed": 0}
    pending = Notification.email_status == "PENDING"
    with SessionLocal() as db:
        planned = db.scalar(select(func.count()).select_from(Notification).where(pending)) or 0
        if not apply:
            return {"dry_run": True, "disabled": False, "planned": planned, "sent": None, "failed": None}
        counts = {"sent": 0, "failed": 0, "skipped": 0, "retry": 0}
        server = connect()
        try:
            while True:
                rows = db.execute(
                    select(Notification, User).join(User, User.id == Notification.recipient_id).where(pending)
                    .order_by(Notification.created_at).limit(BATCH)
                    .with_for_update(of=Notification, skip_locked=True)
                ).all()
                for row, user in rows:
                    if user.status != "ACTIVE":
                        row.email_status = "SKIPPED"
                        counts["skipped"] += 1
                        continue
                    try:
                        server.send_message(message(user.email))
                    except (smtplib.SMTPException, OSError):
                        row.email_attempts += 1
                        row.email_status = "FAILED" if row.email_attempts >= MAX_ATTEMPTS else "PENDING"
                        counts["failed" if row.email_status == "FAILED" else "retry"] += 1
                        continue
                    row.email_status, row.email_sent_at = "SENT", datetime.now(UTC)
                    counts["sent"] += 1
                db.commit()
                if len(rows) < BATCH or counts["retry"]:
                    break
        finally:
            server.quit()
        db.add(AuditEvent(actor_id=None, action="NOTIFICATION_EMAILS_SENT", target_type="system", target_id=None,
                          safe_metadata=counts, request_id=str(uuid.uuid4())))
        db.commit()
        return {"dry_run": False, "disabled": False, "planned": planned, **counts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    print(dispatch(apply=parser.parse_args().apply))
