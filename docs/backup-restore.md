# Backup and isolated recovery

Implemented operator utility: `ops/backup.py`. Requires Python 3.12+ and running Docker Compose DB/API. Backups contain sensitive documents and authentication data; keep the ignored `backups/` directory private and transfer/archive it encrypted using your organization's storage policy. No encryption key or production secret is committed.

```powershell
python ops/backup.py backup backups/2026-10-07-example
python ops/backup.py verify backups/2026-10-07-example --database nexora_restore_test_example
```

Backup refuses an existing destination. It records a PostgreSQL custom dump before packaging immutable private blobs, plus compose.yaml/.env.example and SHA-256 manifest. Actual `.env` is never copied; escrow runtime secrets separately in an encrypted secret manager. Extra unreferenced blobs can be included, but every DB-referenced version must be present. There is no legal purge, so snapshot references remain recoverable while the storage copy runs. Concurrent orphan cleanup must not run during backup until a shared maintenance lock exists.

Verification checks the manifest, only extracts regular key-shaped files without overwriting, creates a NEW database with the restricted `nexora_restore_test_` prefix, restores with exit-on-error, and checks every referenced version's exact size/SHA-256. Existing restore databases are refused. It leaves the test DB and extracted private files available for review; remove them only under your maintenance policy. A failed command is a failed backup/verification, even if partial artifacts exist. Never restore over the live database to test recovery.

## Actual verification, 2026-10-07
`backups/2026-10-07-workflow` restored into `nexora_restore_test_workflow`: 2 documents, 3 versions, 35 audit events, 1 workflow, 3 workflow events. All 3 referenced blobs matched size/SHA-256. A separate API at 127.0.0.1:8890 upgraded the restored schema to head, authenticated the synthetic admin, listed both documents and downloaded all 3 versions over HTTP with exact checksum checks. That temporary API was stopped; the primary DB/storage were not replaced. Restore artifacts are ignored and not committed.

This proves recovery for this small snapshot, not a production RPO/RTO or disaster recovery certification. Scheduling, encrypted remote transport, key escrow, full current-settings backup, large restore, concurrent backup/cleanup locking and recovery rehearsals remain pending. Current utility stores base Compose configuration only; retain deployment overlays, immutable image digests and operational secret references alongside production backups separately.
