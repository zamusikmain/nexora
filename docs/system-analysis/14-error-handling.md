# Error Handling & Edge Cases

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Envelope: `{ "error": "code", "request_id": "uuid" }`. Validation handler скрывает детали input. 500 содержит server_error, log только exception class; это уменьшает утечку, но ограничивает диагностику. 400 Bad Request как собственный бизнес-ответ не найден: не считается реализованным; transport/framework malformed requests могут отличаться.

| Сценарий | Ожидаемое / фактическое поведение | Расхождение |
|---|---|---|
| Repeat request | Тот же actor/key/payload → сохранённый результат, другой payload →409 | Нет expiry; рост таблицы — gap |
| Concurrent PATCH | Один revision побеждает, второй409 | Нужен UI refresh после stale |
| Repeat approval | Replay через WorkflowEvent / own receipt; no double decision | Проверяются нынешние права; не perpetually valid URL |
| Deleted/trash | Nonowner/grants не читают; owner restore с CAS | Soft delete не уничтожает bytes |
| No permission | Скрытый ресурс404, session401, явный permission403 | Разный код зависит от handler/context |
| Wrong workflow scope | 409workflow_scope_changed/invalid_transition | Не допускается решение другой версии |
| DB error | ready503; обычный request500 и rollback при close | Нет всех DB ошибок в granular catalog |
| Scanner unavailable | upload503, quarantine cleaned; retry допустим после recovery | Нет automatic retry |
| Missing/corrupt file | 503file_unavailable, байты не выдаются | Нет repair endpoint |

## Подтверждённые HTTPException sites

Middleware и exception handlers дополнительно возвращают: 403 `origin_forbidden`, 413 `file_too_large`, 422 `validation_error`, 500 `server_error`. Это не прямые HTTPException sites: [main.py:35](../../apps/api/app/main.py#L35) и [body_limit.py](../../apps/api/app/body_limit.py). Их envelope и request_id входят в общий контракт.

Каждая строка — участок исходного кода, не обещание, что все endpoints возвращают этот code. Динамические expressions сохранены как expressions. 413/429/503 также подтверждены. Дополнительные ошибки FastAPI input →422validation_error и middleware→500server_error описаны отдельно.

| Status expression | Error code / expression | Source |
|---|---|---|
| `404` | `'not_found'` | [apps/api/app/access.py:105](../../apps/api/app/access.py#L105) |
| `409` | `'document_in_trash'` | [apps/api/app/access.py:117](../../apps/api/app/access.py#L117) |
| `422` | `'invalid_grant_target'` | [apps/api/app/access.py:123](../../apps/api/app/access.py#L123) |
| `422` | `'invalid_grant_duration'` | [apps/api/app/access.py:126](../../apps/api/app/access.py#L126) |
| `422` | `'invalid_grant_actions'` | [apps/api/app/access.py:128](../../apps/api/app/access.py#L128) |
| `422` | `'review_grant_required'` | [apps/api/app/access.py:152](../../apps/api/app/access.py#L152) |
| `422` | `'invalid_grant_target'` | [apps/api/app/access.py:158](../../apps/api/app/access.py#L158) |
| `409` | `'snapshot_unavailable'` | [apps/api/app/access.py:163](../../apps/api/app/access.py#L163) |
| `404` | `'not_found'` | [apps/api/app/access.py:192](../../apps/api/app/access.py#L192) |
| `404` | `'not_found'` | [apps/api/app/access.py:207](../../apps/api/app/access.py#L207) |
| `422` | `'invalid_grant_actions'` | [apps/api/app/access.py:212](../../apps/api/app/access.py#L212) |
| `404` | `'not_found'` | [apps/api/app/access.py:259](../../apps/api/app/access.py#L259) |
| `404` | `'not_found'` | [apps/api/app/access.py:265](../../apps/api/app/access.py#L265) |
| `403` | `'self_approval_forbidden'` | [apps/api/app/access.py:267](../../apps/api/app/access.py#L267) |
| `409` | `'grant_scope_changed'` | [apps/api/app/access.py:271](../../apps/api/app/access.py#L271) |
| `409` | `'grant_not_pending'` | [apps/api/app/access.py:274](../../apps/api/app/access.py#L274) |
| `409` | `'grant_scope_changed'` | [apps/api/app/access.py:276](../../apps/api/app/access.py#L276) |
| `409` | `'grant_scope_changed'` | [apps/api/app/access.py:281](../../apps/api/app/access.py#L281) |
| `409` | `'duplicate_endorsement'` | [apps/api/app/access.py:284](../../apps/api/app/access.py#L284) |
| `403` | `'forbidden'` | [apps/api/app/access.py:286](../../apps/api/app/access.py#L286) |
| `404` | `'not_found'` | [apps/api/app/access.py:312](../../apps/api/app/access.py#L312) |
| `404` | `'not_found'` | [apps/api/app/access.py:317](../../apps/api/app/access.py#L317) |
| `404` | `'not_found'` | [apps/api/app/access.py:329](../../apps/api/app/access.py#L329) |
| `404` | `'not_found'` | [apps/api/app/access.py:346](../../apps/api/app/access.py#L346) |
| `409` | `'department_review_disabled'` | [apps/api/app/access.py:350](../../apps/api/app/access.py#L350) |
| `422` | `'invalid_grant_target'` | [apps/api/app/access.py:353](../../apps/api/app/access.py#L353) |
| `404` | `'not_found'` | [apps/api/app/access.py:372](../../apps/api/app/access.py#L372) |
| `404` | `'not_found'` | [apps/api/app/access.py:375](../../apps/api/app/access.py#L375) |
| `409` | `'receipt_already_revoked'` | [apps/api/app/access.py:377](../../apps/api/app/access.py#L377) |
| `404` | `'not_found'` | [apps/api/app/access.py:387](../../apps/api/app/access.py#L387) |
| `404` | `'not_found'` | [apps/api/app/access.py:390](../../apps/api/app/access.py#L390) |
| `404` | `'not_found'` | [apps/api/app/access.py:425](../../apps/api/app/access.py#L425) |
| `422` | `'invalid_grant_target'` | [apps/api/app/access.py:136](../../apps/api/app/access.py#L136) |
| `409` | `'approval_not_active'` | [apps/api/app/access.py:140](../../apps/api/app/access.py#L140) |
| `422` | `'invalid_grant_actions'` | [apps/api/app/access.py:144](../../apps/api/app/access.py#L144) |
| `422` | `'invalid_grant_target'` | [apps/api/app/access.py:150](../../apps/api/app/access.py#L150) |
| `409` | `'approval_not_active'` | [apps/api/app/access.py:292](../../apps/api/app/access.py#L292) |
| `404` | `'not_found'` | [apps/api/app/access.py:393](../../apps/api/app/access.py#L393) |
| `409` | `'snapshot_unavailable'` | [apps/api/app/access.py:148](../../apps/api/app/access.py#L148) |
| `409` | `'grant_scope_changed'` | [apps/api/app/access.py:301](../../apps/api/app/access.py#L301) |
| `401` | `'unauthorized'` | [apps/api/app/auth.py:34](../../apps/api/app/auth.py#L34) |
| `401` | `'unauthorized'` | [apps/api/app/auth.py:37](../../apps/api/app/auth.py#L37) |
| `429` | `'login_rate_limited'` | [apps/api/app/auth.py:81](../../apps/api/app/auth.py#L81) |
| `401` | `'invalid_credentials'` | [apps/api/app/auth.py:93](../../apps/api/app/auth.py#L93) |
| `404` | `'not_found'` | [apps/api/app/auth.py:188](../../apps/api/app/auth.py#L188) |
| `404` | `'not_found'` | [apps/api/app/auth.py:201](../../apps/api/app/auth.py#L201) |
| `403` | `'csrf_failed'` | [apps/api/app/auth.py:42](../../apps/api/app/auth.py#L42) |
| `413` | `'file_too_large'` | [apps/api/app/body_limit.py:25](../../apps/api/app/body_limit.py#L25) |
| `409` | `'self_admin_change'` | [apps/api/app/catalog.py:49](../../apps/api/app/catalog.py#L49) |
| `404` | `'not_found'` | [apps/api/app/catalog.py:52](../../apps/api/app/catalog.py#L52) |
| `409` | `'stale_record'` | [apps/api/app/catalog.py:54](../../apps/api/app/catalog.py#L54) |
| `422` | `'invalid_department'` | [apps/api/app/catalog.py:56](../../apps/api/app/catalog.py#L56) |
| `404` | `'not_found'` | [apps/api/app/catalog.py:157](../../apps/api/app/catalog.py#L157) |
| `409` | `'stale_record'` | [apps/api/app/catalog.py:159](../../apps/api/app/catalog.py#L159) |
| `409` | `'field_in_use'` | [apps/api/app/catalog.py:163](../../apps/api/app/catalog.py#L163) |
| `409` | `'duplicate_code'` | [apps/api/app/catalog.py:146](../../apps/api/app/catalog.py#L146) |
| `409` | `'duplicate_code'` | [apps/api/app/catalog.py:177](../../apps/api/app/catalog.py#L177) |
| `422` | `'invalid_custom_field'` | [apps/api/app/custom_fields.py:142](../../apps/api/app/custom_fields.py#L142) |
| `422` | `'invalid_custom_field'` | [apps/api/app/custom_fields.py:159](../../apps/api/app/custom_fields.py#L159) |
| `404` | `'not_found'` | [apps/api/app/dms.py:57](../../apps/api/app/dms.py#L57) |
| `409` | `'stale_document'` | [apps/api/app/dms.py:63](../../apps/api/app/dms.py#L63) |
| `403` | `'forbidden'` | [apps/api/app/dms.py:68](../../apps/api/app/dms.py#L68) |
| `409` | `'stale_record'` | [apps/api/app/dms.py:120](../../apps/api/app/dms.py#L120) |
| `409` | `'invalid_transition'` | [apps/api/app/dms.py:197](../../apps/api/app/dms.py#L197) |
| `409` | `'invalid_transition'` | [apps/api/app/dms.py:213](../../apps/api/app/dms.py#L213) |
| `404` | `'not_found'` | [apps/api/app/dms.py:234](../../apps/api/app/dms.py#L234) |
| `503` | `'file_unavailable'` | [apps/api/app/dms.py:253](../../apps/api/app/dms.py#L253) |
| `422` | `'diff_unsupported'` | [apps/api/app/dms.py:323](../../apps/api/app/dms.py#L323) |
| `409` | `'folder_depth'` | [apps/api/app/dms.py:89](../../apps/api/app/dms.py#L89) |
| `403` | `'forbidden'` | [apps/api/app/dms.py:104](../../apps/api/app/dms.py#L104) |
| `409` | `'folder_depth'` | [apps/api/app/dms.py:106](../../apps/api/app/dms.py#L106) |
| `403` | `'forbidden'` | [apps/api/app/dms.py:124](../../apps/api/app/dms.py#L124) |
| `409` | `'folder_cycle'` | [apps/api/app/dms.py:127](../../apps/api/app/dms.py#L127) |
| `409` | `'folder_depth'` | [apps/api/app/dms.py:137](../../apps/api/app/dms.py#L137) |
| `403` | `'forbidden'` | [apps/api/app/dms.py:159](../../apps/api/app/dms.py#L159) |
| `503` | `'file_unavailable'` | [apps/api/app/dms.py:250](../../apps/api/app/dms.py#L250) |
| `404` | `'not_found'` | [apps/api/app/dms.py:306](../../apps/api/app/dms.py#L306) |
| `422` | `'diff_unsupported'` | [apps/api/app/dms.py:308](../../apps/api/app/dms.py#L308) |
| `503` | `'file_unavailable'` | [apps/api/app/dms.py:320](../../apps/api/app/dms.py#L320) |
| `503` | `'file_unavailable'` | [apps/api/app/dms.py:317](../../apps/api/app/dms.py#L317) |
| `404` | `'not_found'` | [apps/api/app/documents.py:94](../../apps/api/app/documents.py#L94) |
| `422` | `'invalid_document_type'` | [apps/api/app/documents.py:223](../../apps/api/app/documents.py#L223) |
| `409` | `'stale_document'` | [apps/api/app/documents.py:251](../../apps/api/app/documents.py#L251) |
| `422` | `'invalid_document_type'` | [apps/api/app/documents.py:254](../../apps/api/app/documents.py#L254) |
| `403` | `'classification_change_forbidden'` | [apps/api/app/documents.py:258](../../apps/api/app/documents.py#L258) |
| `403` | `'forbidden'` | [apps/api/app/documents.py:285](../../apps/api/app/documents.py#L285) |
| `409` | `'document_in_trash'` | [apps/api/app/documents.py:289](../../apps/api/app/documents.py#L289) |
| `409` | `'invalid_transition'` | [apps/api/app/documents.py:297](../../apps/api/app/documents.py#L297) |
| `409` | `'file_required'` | [apps/api/app/documents.py:303](../../apps/api/app/documents.py#L303) |
| `404` | `'not_found'` | [apps/api/app/documents.py:423](../../apps/api/app/documents.py#L423) |
| `409` | `'document_not_editable'` | [apps/api/app/documents.py:491](../../apps/api/app/documents.py#L491) |
| `404` | `'not_found'` | [apps/api/app/documents.py:494](../../apps/api/app/documents.py#L494) |
| `422` | `'invalid_responsible'` | [apps/api/app/documents.py:210](../../apps/api/app/documents.py#L210) |
| `422` | `'invalid_dates'` | [apps/api/app/documents.py:263](../../apps/api/app/documents.py#L263) |
| `413` | `'file_too_large'` | [apps/api/app/documents.py:361](../../apps/api/app/documents.py#L361) |
| `404` | `'not_found'` | [apps/api/app/documents.py:368](../../apps/api/app/documents.py#L368) |
| `503` | `'file_unavailable'` | [apps/api/app/documents.py:428](../../apps/api/app/documents.py#L428) |
| `503` | `'file_unavailable'` | [apps/api/app/documents.py:438](../../apps/api/app/documents.py#L438) |
| `503` | `'file_scan_required'` | [apps/api/app/documents.py:539](../../apps/api/app/documents.py#L539) |
| `503` | `'file_unavailable'` | [apps/api/app/documents.py:435](../../apps/api/app/documents.py#L435) |
| `404` | `'not_found'` | [apps/api/app/documents.py:475](../../apps/api/app/documents.py#L475) |
| `422` | `'idempotency_key_required'` | [apps/api/app/idempotency.py:19](../../apps/api/app/idempotency.py#L19) |
| `409` | `'idempotency_conflict'` | [apps/api/app/idempotency.py:37](../../apps/api/app/idempotency.py#L37) |
| `409` | `'idempotency_conflict'` | [apps/api/app/idempotency.py:43](../../apps/api/app/idempotency.py#L43) |
| `409` | `'idempotency_conflict'` | [apps/api/app/idempotency.py:70](../../apps/api/app/idempotency.py#L70) |
| `422` | `'invalid_idempotency_key'` | [apps/api/app/idempotency.py:23](../../apps/api/app/idempotency.py#L23) |
| `409` | `'idempotency_conflict'` | [apps/api/app/idempotency.py:46](../../apps/api/app/idempotency.py#L46) |
| `503` | `'database_unavailable'` | [apps/api/app/main.py:89](../../apps/api/app/main.py#L89) |
| `403` | `'forbidden'` | [apps/api/app/policy.py:30](../../apps/api/app/policy.py#L30) |
| `404` | `'not_found'` | [apps/api/app/policy.py:177](../../apps/api/app/policy.py#L177) |
| `403` | `'forbidden'` | [apps/api/app/policy.py:182](../../apps/api/app/policy.py#L182) |
| `409` | `'document_in_trash'` | [apps/api/app/policy.py:184](../../apps/api/app/policy.py#L184) |
| `409` | `'document_not_editable'` | [apps/api/app/policy.py:186](../../apps/api/app/policy.py#L186) |
| `503` | `'scanner_unavailable'` | [apps/api/app/scanning.py:21](../../apps/api/app/scanning.py#L21) |
| `503` | `'scanner_unavailable'` | [apps/api/app/scanning.py:62](../../apps/api/app/scanning.py#L62) |
| `422` | `'malware_detected'` | [apps/api/app/scanning.py:59](../../apps/api/app/scanning.py#L59) |
| `422` | `'invalid_filename'` | [apps/api/app/storage.py:56](../../apps/api/app/storage.py#L56) |
| `422` | `'unsupported_file'` | [apps/api/app/storage.py:64](../../apps/api/app/storage.py#L64) |
| `422` | `'invalid_file_type'` | [apps/api/app/storage.py:66](../../apps/api/app/storage.py#L66) |
| `422` | `'empty_file'` | [apps/api/app/storage.py:78](../../apps/api/app/storage.py#L78) |
| `422` | `'invalid_file_content'` | [apps/api/app/storage.py:131](../../apps/api/app/storage.py#L131) |
| `413` | `'file_too_large'` | [apps/api/app/storage.py:74](../../apps/api/app/storage.py#L74) |
| `409` | `'idempotency_conflict'` | [apps/api/app/workflows.py:211](../../apps/api/app/workflows.py#L211) |
| `404` | `'not_found'` | [apps/api/app/workflows.py:316](../../apps/api/app/workflows.py#L316) |
| `403` | `'forbidden'` | [apps/api/app/workflows.py:333](../../apps/api/app/workflows.py#L333) |
| `409` | `'stale_document'` | [apps/api/app/workflows.py:341](../../apps/api/app/workflows.py#L341) |
| `409` | `'invalid_transition'` | [apps/api/app/workflows.py:343](../../apps/api/app/workflows.py#L343) |
| `409` | `'file_required'` | [apps/api/app/workflows.py:345](../../apps/api/app/workflows.py#L345) |
| `422` | `'invalid_workflow_template'` | [apps/api/app/workflows.py:351](../../apps/api/app/workflows.py#L351) |
| `409` | `'required_workflow'` | [apps/api/app/workflows.py:354](../../apps/api/app/workflows.py#L354) |
| `409` | `'required_stage_condition'` | [apps/api/app/workflows.py:356](../../apps/api/app/workflows.py#L356) |
| `422` | `'invalid_workflow_target'` | [apps/api/app/workflows.py:384](../../apps/api/app/workflows.py#L384) |
| `422` | `'empty_workflow'` | [apps/api/app/workflows.py:386](../../apps/api/app/workflows.py#L386) |
| `404` | `'not_found'` | [apps/api/app/workflows.py:423](../../apps/api/app/workflows.py#L423) |
| `409` | `'workflow_not_running'` | [apps/api/app/workflows.py:443](../../apps/api/app/workflows.py#L443) |
| `409` | `'document_in_trash'` | [apps/api/app/workflows.py:463](../../apps/api/app/workflows.py#L463) |
| `409` | `'workflow_scope_changed'` | [apps/api/app/workflows.py:465](../../apps/api/app/workflows.py#L465) |
| `422` | `'approval_comment_required'` | [apps/api/app/workflows.py:483](../../apps/api/app/workflows.py#L483) |
| `404` | `'not_found'` | [apps/api/app/workflows.py:615](../../apps/api/app/workflows.py#L615) |
| `404` | `'not_found'` | [apps/api/app/workflows.py:621](../../apps/api/app/workflows.py#L621) |
| `409` | `'idempotency_conflict'` | [apps/api/app/workflows.py:309](../../apps/api/app/workflows.py#L309) |
| `422` | `'unauthorized_reviewer'` | [apps/api/app/workflows.py:379](../../apps/api/app/workflows.py#L379) |
| `422` | `'invalid_workflow_target'` | [apps/api/app/workflows.py:381](../../apps/api/app/workflows.py#L381) |
| `404` | `'not_found'` | [apps/api/app/workflows.py:438](../../apps/api/app/workflows.py#L438) |
| `404` | `'not_found'` | [apps/api/app/workflows.py:455](../../apps/api/app/workflows.py#L455) |
| `403 if doc.owner_id == user.id else 404` | `'not_assigned_approval'` | [apps/api/app/workflows.py:458](../../apps/api/app/workflows.py#L458) |
| `403` | `'unauthorized_reviewer'` | [apps/api/app/workflows.py:476](../../apps/api/app/workflows.py#L476) |
| `409` | `'workflow_scope_changed'` | [apps/api/app/workflows.py:481](../../apps/api/app/workflows.py#L481) |
| `422` | `'invalid_workflow_target'` | [apps/api/app/workflows.py:157](../../apps/api/app/workflows.py#L157) |
| `403` | `'access_required'` | [apps/api/app/workflows.py:461](../../apps/api/app/workflows.py#L461) |
