# Notifications, overdue escalation and email outbox

Migration `0011_notifications` adds the `notifications` table and `approvals.escalated_at`.

## In-app notifications

Rows are written **in the same transaction** as the workflow change that caused them (start, decision, cancellation, escalation). A failed or rolled-back action produces no notification; a committed one can't lose it. A unique key `(recipient_id, dedupe_key)` keeps retries from creating duplicates. Nobody is notified about their own action.

| Kind | Recipient | When |
|---|---|---|
| `TASK_ASSIGNED` | assignee | a stage becomes active for them (start or previous stage completed) |
| `TASK_CANCELLED` | assignee | their open task was withdrawn (rejection, return, cancellation) |
| `WORKFLOW_APPROVED` / `WORKFLOW_REJECTED` / `WORKFLOW_RETURNED` | document owner | the workflow ends with that outcome |
| `TASK_OVERDUE` | assignee | escalation run, deadline passed |
| `WORKFLOW_OVERDUE` | document owner | escalation run, a task of their workflow is overdue |
| `TASK_ESCALATED` | active managers of the assignee's department (active admins if none) | escalation run |

A row stores identifiers only. Document number and title are resolved **when the recipient reads the list**, through the normal ACL (`can_read(..., "card")`). If the recipient can't read the card right now, the item shows "document not available" with no number or title. For example, a manager receives an escalation for a document still in approval. Such an item shows only the assignee's name and the deadline.

API (session + CSRF; read-state changes need no retry key because they are idempotent):

- `GET /api/v1/notifications?unread=&page=` — 20 per page, plus the unread count
- `GET /api/v1/notifications/summary` — `{unread}`; the sidebar polls it every 60 s and on focus
- `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all` — 204. A foreign id gets 404.

The runtime role gets `SELECT, INSERT` on `notifications` and `UPDATE` only on `read_at, email_status, email_attempts, email_sent_at`. Recipient, kind and document can't be rewritten, and rows can't be deleted. Re-run role provisioning after the migration.

## Overdue escalation

`python -m app.workflow_escalation` is a dry run (it only counts); `--apply` escalates. Each overdue task of a running stage is escalated **once**: it sets `escalated_at`, writes the three notifications above and audits `WORKFLOW_ESCALATED` with counts only. Rows are claimed with `FOR UPDATE SKIP LOCKED`, so a task being decided right now is left for the next run.

Escalation only informs. It does not reassign, extend or decide tasks; reassignment and delegation are not implemented. Run it from the operator's scheduler (for example every 15 minutes). No built-in worker or scheduler exists.

## Email outbox

Email is off unless `SMTP_HOST` is set. When it is set, new notifications are created with `email_status = PENDING`. `python -m app.notification_dispatch` (dry run; `--apply` sends) then delivers them over SMTP:

- STARTTLS is required in production;
- `SMTP_FROM` must be an address;
- `SMTP_USERNAME` and `SMTP_PASSWORD` are optional and come from the environment.

Emails deliberately carry **no document number, title or comment**: mail leaves the trust boundary. The message only says that a notification is waiting and links to `/notifications`, where the ACL applies.

Delivery is at least once: a crash between sending and committing can repeat one email. A failed send is retried on later runs and marked `FAILED` after 5 attempts. Inactive recipients are `SKIPPED`. Each run audits `NOTIFICATION_EMAILS_SENT` with counts.

## Not implemented

- per-user notification preferences;
- digest emails;
- push or websocket delivery;
- retention purge of old notifications;
- reassignment or delegation on escalation;
- notifications for comments, access requests and grants.
