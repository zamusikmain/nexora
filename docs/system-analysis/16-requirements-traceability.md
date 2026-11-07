# Requirements Traceability Matrix

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

API идентификаторы — точные method/path из FastAPI. Для FR-018 отдельного серверного теста локализации нет: Missing Test здесь относится к этой связи; frontend проверки перечислены отдельно.

| BR | FR | US | API | Entity | Test Case | Status |
|---|---|---|---|---|---|---|
| BR-001 | FR-001 | US-001 | `POST /api/v1/documents` | `documents` | [apps/api/tests/test_api.py:166](../../apps/api/tests/test_api.py#L166) `test_document_versions_lifecycle_audit_bola` | Implemented |
| BR-001 | FR-002 | US-002 | `PATCH /api/v1/documents/{doc_id}` | `documents` | [apps/api/tests/test_hardening.py:148](../../apps/api/tests/test_hardening.py#L148) `test_partial_patch_preserves_metadata_and_requires_revision` | Implemented |
| BR-002 | FR-003 | US-003 | `POST /api/v1/documents/{doc_id}/versions` | `document_versions` | [apps/api/tests/test_hardening.py:219](../../apps/api/tests/test_hardening.py#L219) `test_parallel_upload_has_one_blob_version_and_audit` | Implemented |
| BR-002 | FR-004 | US-004 | `GET /api/v1/documents/{doc_id}/versions/{version_id}/download` | `document_versions` | [apps/api/tests/test_acl_contracts.py:55](../../apps/api/tests/test_acl_contracts.py#L55) `test_foreign_download_diff_and_version_binding_denied` | Implemented |
| BR-003 | FR-005 | US-005 | `GET /api/v1/documents` | `documents` | [apps/api/tests/test_acl_contracts.py:68](../../apps/api/tests/test_acl_contracts.py#L68) `test_unreadable_document_is_absent_from_search_and_dashboard` | Implemented |
| BR-004 | FR-006 | US-006 | `POST /api/v1/documents/{doc_id}/workflows` | `workflow_instances` | [apps/api/tests/test_hardening.py:279](../../apps/api/tests/test_hardening.py#L279) `test_required_route_blocks_shortcut_and_rechecks_reviewer` | Implemented |
| BR-004 | FR-007 | US-007 | `POST /api/v1/workflows/{instance_id}/decisions` | `approvals` | [apps/api/tests/test_api.py:508](../../apps/api/tests/test_api.py#L508) `test_workflow_parallel_snapshots_bola_and_idempotency` | Implemented |
| BR-004 | FR-008 | US-008 | `POST /api/v1/workflows/{instance_id}/decisions` | `workflow_events` | [apps/api/tests/test_api.py:587](../../apps/api/tests/test_api.py#L587) `test_workflow_revision_rejection_cancel_conditions_and_concurrency` | Implemented |
| BR-004 | FR-009 | US-009 | `POST /api/v1/workflow-templates` | `workflow_templates` | [apps/api/tests/test_hardening.py:50](../../apps/api/tests/test_hardening.py#L50) `test_required_route_rejects_unauthorized_roles_and_conditional_stages` | Partially implemented |
| BR-005 | FR-010 | US-010 | `POST /api/v1/documents/{doc_id}/access-requests` | `access_grants` | [apps/api/tests/test_acl_live.py:227](../../apps/api/tests/test_acl_live.py#L227) `test_personal_grant_revoke_and_no_new_version` | Implemented |
| BR-005 | FR-011 | US-011 | `POST /api/v1/access/grants/{grant_id}/endorse` | `grant_endorsements` | [apps/api/tests/test_acl_live.py:249](../../apps/api/tests/test_acl_live.py#L249) `test_restricted_no_self_approval_duplicate_vote_or_scope_mutation` | Implemented |
| BR-005 | FR-012 | US-012 | `POST /api/v1/access/grants/{grant_id}/revoke` | `access_grants` | [apps/api/tests/test_acl_live.py:270](../../apps/api/tests/test_acl_live.py#L270) `test_expired_grant_and_authority_are_denied_on_every_request` | Implemented |
| BR-005 | FR-013 | US-013 | `POST /api/v1/documents/{doc_id}/department-review` | `acl_department_policies` | [apps/api/tests/test_acl_live.py:286](../../apps/api/tests/test_acl_live.py#L286) `test_manager_draft_handoff_captures_people_and_revokes_with_new_version` | Implemented |
| BR-005 | FR-014 | US-014 | `GET /api/v1/approvals/{approval_id}/receipt` | `review_receipts` | [apps/api/tests/test_acl_live.py:365](../../apps/api/tests/test_acl_live.py#L365) `test_own_snapshot_no_other_stages_and_seven_day_expiry` | Implemented |
| BR-006 | FR-015 | US-015 | `POST /api/v1/documents/{doc_id}/comments` | `comments` | [apps/api/tests/test_acl_live.py:107](../../apps/api/tests/test_acl_live.py#L107) `test_owner_replies_are_visible_only_to_their_current_review_stage` | Implemented |
| BR-002 | FR-016 | US-016 | `POST /api/v1/documents/{doc_id}/versions/{version_id}/restore` | `folders` | [apps/api/tests/test_api.py:324](../../apps/api/tests/test_api.py#L324) `test_dms_folders_trash_favorites_revision_restore_diff` | Implemented |
| BR-007 | FR-017 | US-017 | `PATCH /api/v1/users/{user_id}` | `users` | [apps/api/tests/test_api.py:724](../../apps/api/tests/test_api.py#L724) `test_session_inventory_scoping_revocation_and_admin` | Implemented |
| BR-008 | FR-018 | US-018 | `GET /api/v1/approvals` | `approvals` | Missing Test | Partially implemented |
