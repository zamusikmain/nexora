# Architecture decisions — 2026-10-07

## Incremental delivery
Retain the modular monolith and immutable PostgreSQL history. Each increment adds migrations after 0001, API authorization, UI, localization and integration tests. Completion of this increment does not imply commercial release readiness.

## Folders and access
Folders are private, owned namespaces. Administrators can inspect them. Placing a document in a folder does not grant access or revoke existing departmental access. This avoids implicit ACL escalation while granular ACL is being designed. Parent/child ownership must match. PostgreSQL transaction advisory locks serialize tree mutations per owner; recursive ancestry and subtree depth checks prevent cycles and excessive depth even under concurrent moves. Root structure is a private workspace, not yet a company-wide hierarchy.

## Trash and immutable history
Soft deletion preserves state, comments, audit and immutable versions. In-progress processes cannot be trashed. No automatic retention or physical purge is exposed: the existing version DELETE trigger deliberately makes physical document deletion impossible. An authorized, legally reviewed retention policy and separate purge ledger are prerequisites for future physical removal. Trash has no claim of erasure compliance.

## Blob/database consistency
A failed commit acknowledgement does not establish rollback. Keep a newly written blob on database exceptions rather than risk deleting a committed document version. Future cleanup must first successfully query a complete live-reference set and respect a grace period. Restore copies and validates old bytes into a new key and immutable row; a checksum mismatch fails closed.

## Metadata revisions
New UI writes carry the loaded document revision. Move, trash and restore require it and reject stale requests. Legacy metadata PATCH requests remain accepted without it for compatibility; strict revision enforcement is a release prerequisite for all clients.

## Planned foundations
Workflow templates must be immutable snapshots and instances must bind both document version and metadata. Steps need row-lock serialization plus persisted idempotency keys. ACL must have one SQL policy reused by list/search/analytics/export/AI. Workers should use a transactional outbox and bounded retry, never in-memory-only delivery. Tenancy needs explicit organization keys plus database-level isolation before SaaS deployment. Local storage remains private; S3 and scanners must use the same authorization and integrity contracts. AI retrieval must authorize before parsing or calling a provider. None of these planned decisions constitutes an implemented feature.
