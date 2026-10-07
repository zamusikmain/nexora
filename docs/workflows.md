# Workflow engine

Implemented: immutable versioned templates; document/version/metadata snapshot; sequential stages with unanimous parallel assignments; user, role or department selectors resolved once at start; deadlines set when a stage activates; required comments; approve, reject, return for revision, owner/admin cancellation; resubmission creates a new instance against the new file and metadata. Owner cannot approve their own document. No empty assigned stage or all-skipped workflow is silently approved.

Conditions are declarative AND clauses over metadata.<key> and confidentiality. Operators eq/ne/gt/gte/lt/lte/in; comparisons are typed, missing numeric values skip the stage, no expression evaluation. Administrator UI currently supports one condition per stage; API supports up to 10. Exact type equality distinguishes booleans from numbers. Numeric inequalities support both integer and float.

Constraints: at most 20 stages, 100 active users per stage and 200 assignments in one process. User directory and template lists are bounded (500/100); large organizations need paginated administration before release.

Concurrency: document row is locked first, then instance and assignments. One active instance per document enforced by a partial unique index. Start and decisions require UUID idempotency keys, persisted per actor together with a SHA-256 request fingerprint; retries with identical payload return the instance, changed payload with the same key returns 409. Concurrent same-key approvals record one decision. Document edits/uploads are rejected while IN_APPROVAL. New UI preserves retry keys after a failed network request in the current page session; persisted offline retry is not implemented.

Integrity: PostgreSQL rejects template/history UPDATE and DELETE and prevents changes to instance document/version/template/metadata/initiator/time. Immutable events plus transactional audit record decisions and required reasons. Old templates remain readable through their bound instance; creating a newer version never changes running processes.

Access: a resolved assignment grants read access to the related document, including history, comments and exact downloads, using the same SQL visibility predicate as lists and dashboard. Decisions still require that actor’s pending assignment for the current stage; ADMIN has no unassigned approval override. Durable participant document read is the current explicit policy, including completed processes. Fine-grained revocation, scoped historical snapshots, resource ACL, groups, manager selectors and delegation remain release work; this policy must be approved for a company pilot.

UI: administrator template builder, document start/decision/history panel, My Approvals with pending/completed/rejected/overdue and server pagination. UI only shows implemented selector types. Native confirmations remain in legacy lifecycle/DMS actions; decision reasons are submitted explicitly.

New API: GET/POST /workflow-templates; GET/POST /documents/{id}/workflows; POST /workflows/{id}/decisions; GET /approvals?view=pending|completed|rejected|overdue&page=.

Not implemented: group/manager routing, delegation, notification/email delivery, escalations, arbitrary branching/loops, quorum approvals and reassignment. No claim of a complete enterprise workflow suite.
