# Acceptance Criteria

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Сценарии ниже являются проверяемыми критериями, не заявлением о выполненном browser UAT. AC-N01…03 — дополнительные границы.

## AC-001 — Регистрация документа

Given ACTIVE сессия и существующий document type. When создать карточку с title, type_id и валидными метаданными. Then создана карточка DRAFT с revision=1.

Negative: Given тот же actor и нарушенное условие (422 invalid_document_type; одинаковый ключ с другим телом → 409). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When можно создать карточку без файла; на отправке файл обязателен. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_api.py:166](../../apps/api/tests/test_api.py#L166) `test_document_versions_lifecycle_audit_bola`.

## AC-002 — Редактирование и конкуренция

Given ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash. When отправить PATCH с expected_revision. Then revision увеличена; старые версии не переписаны.

Negative: Given тот же actor и нарушенное условие (409 stale_document; null title → 422; RESTRICTED downgrade → 403). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When непереданные поля сохраняются; nullable custom field можно очистить null. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_hardening.py:148](../../apps/api/tests/test_hardening.py#L148) `test_partial_patch_preserves_metadata_and_requires_revision`.

## AC-003 — Файлы и версии

Given ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash. When передать multipart file и change_note. Then immutable версия и current_version_id; scanner attestation в production.

Negative: Given тот же actor и нарушенное условие (413 размер; 422 malware_detected; 503 scanner_unavailable). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When после неизвестного ответа повтор с тем же ключом возвращает ту же версию. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_hardening.py:219](../../apps/api/tests/test_hardening.py#L219) `test_parallel_upload_has_one_blob_version_and_audit`.

## AC-004 — Приватное чтение файла

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When скачать конкретную версию. Then скачаны только разрешённые байты.

Negative: Given тот же actor и нарушенное условие (404 скрывает существование; 503 file_unavailable). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When owner видит свои старые версии; остальные только разрешённые. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_contracts.py:55](../../apps/api/tests/test_acl_contracts.py#L55) `test_foreign_download_diff_and_version_binding_denied`.

## AC-005 — Списки, поиск, dashboard

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When запросить список / поиск. Then чужие недоступные карточки не возвращены.

Negative: Given тот же actor и нарушенное условие (401 неактивная сессия; 422 неверный page/page_size). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When my/favorites/archive/trash; dashboard по доступным карточкам. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_contracts.py:68](../../apps/api/tests/test_acl_contracts.py#L68) `test_unreadable_document_is_absent_from_search_and_dashboard`.

## AC-006 — Запуск согласования

Given ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash. When выбрать template_id, expected_revision и UUID в body. Then iN_APPROVAL; версия, шаблон и план закреплены.

Negative: Given тот же actor и нарушенное условие (409 required_workflow/stale_document; 422 invalid_workflow_target). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When условные этапы допустимы для необязательного маршрута; optional submit даёт SUBMITTED. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_hardening.py:279](../../apps/api/tests/test_hardening.py#L279) `test_required_route_blocks_shortcut_and_rechecks_reviewer`.

## AC-007 — Решение и единогласие

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When action=approve и idempotency_key. Then личное решение записано один раз; доступ участника прекращён.

Negative: Given тот же actor и нарушенное условие (404 чужое назначение; 403 access_required; 409 workflow_scope_changed). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When при последнем этапе документ APPROVED; тот же ключ возвращает собственную квитанцию. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_api.py:508](../../apps/api/tests/test_api.py#L508) `test_workflow_parallel_snapshots_bola_and_idempotency`.

## AC-008 — Возврат, отклонение, отмена

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When action=revision/reject/cancel с комментарием. Then история прежнего процесса сохранена.

Negative: Given тот же actor и нарушенное условие (422 approval_comment_required; 409 invalid_transition). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When rEVISION_REQUIRED позволяет редактирование и новый процесс; REJECTED не имеет пути прямого resubmit. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_api.py:587](../../apps/api/tests/test_api.py#L587) `test_workflow_revision_rejection_cancel_conditions_and_concurrency`.

## AC-009 — Шаблоны и обязательный маршрут

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When создать новую версию маршрута; оператор отдельно задаёт type policy. Then старые instances остаются на прежнем шаблоне.

Negative: Given тот же actor и нарушенное условие (422 unauthorized_reviewer; 409 required_stage_condition). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When без requirement владелец выбирает template; условия не допускаются в required route. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_hardening.py:50](../../apps/api/tests/test_hardening.py#L50) `test_required_route_rejects_unauthorized_roles_and_conditional_stages`.

## AC-010 — Персональный временный допуск

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When задать лицо, version_id, actions, purpose, reason, hours. Then допуск привязан к версии и проверяется на каждом запросе.

Negative: Given тот же actor и нарушенное условие (422 invalid_grant_target/duration; trash → 409). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When cUSTODIAN request требует подтверждение; grants не переходят на новую версию. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_live.py:227](../../apps/api/tests/test_acl_live.py#L227) `test_personal_grant_revoke_and_no_new_version`.

## AC-011 — Два одобрения RESTRICTED

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When подтвердить office и scope_hash. Then aCTIVE только после двух разных лиц.

Negative: Given тот же actor и нарушенное условие (403 self_approval_forbidden; 409 duplicate_endorsement/grant_scope_changed). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When первый голос оставляет PENDING; срок ≤8 часов от активации. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_live.py:249](../../apps/api/tests/test_acl_live.py#L249) `test_restricted_no_self_approval_duplicate_vote_or_scope_mutation`.

## AC-012 — Срок и отзыв допуска

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When отозвать с reason либо достичь expires_at. Then новые чтения и скачивания запрещены.

Negative: Given тот же actor и нарушенное условие (404 чужой grant; изменение роли/отдела лишает допуска). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When повтор terminal revoke не добавляет повторный аудит; GET grants материализует EXPIRED до 100 строк. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_live.py:270](../../apps/api/tests/test_acl_live.py#L270) `test_expired_grant_and_authority_are_denied_on_every_request`.

## AC-013 — Черновики MANAGER

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When передать текущую версию отдела на review. Then новые managers/версии не наследуют старый допуск.

Negative: Given тот же actor и нарушенное условие (409 department_review_disabled; 422 invalid_grant_target). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When aPPROVED PUBLIC/INTERNAL доступен MANAGER своего отдела без draft handoff. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_live.py:286](../../apps/api/tests/test_acl_live.py#L286) `test_manager_draft_handoff_captures_people_and_revokes_with_new_version`.

## AC-014 — Квитанции и снимок проверки

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When открыть собственную завершённую задачу. Then нет файла, актуальной карточки или чужих комментариев.

Negative: Given тот же actor и нарушенное условие (404 чужая/скрытая квитанция; revoked snapshot исключён). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When nonrestricted snapshot <7 дней пока процесс RUNNING; иначе нужен snapshot grant; restricted всегда отдельный допуск. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_live.py:365](../../apps/api/tests/test_acl_live.py#L365) `test_own_snapshot_no_other_stages_and_seven_day_expiry`.

## AC-015 — Комментарии и история

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When оставить комментарий или запросить разрешённый раздел. Then содержимое и аудит не раскрывают другие scopes.

Negative: Given тот же actor и нарушенное условие (404 нет доступа; 409 document_not_editable для archive/trash). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When owner видит весь поток; участник только свой текущий scope; карточка не даёт историю. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_acl_live.py:107](../../apps/api/tests/test_acl_live.py#L107) `test_owner_replies_are_visible_only_to_their_current_review_stage`.

## AC-016 — Папки, корзина, восстановление

Given ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash. When изменить организацию или восстановить версию с expected_revision. Then исходные версии и аудит сохранены.

Negative: Given тот же actor и нарушенное условие (409 folder_cycle/stale_document; 422 diff_unsupported). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When favorites PUT/DELETE идемпотентны; TXT diff требует file+compare обеих версий. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_api.py:324](../../apps/api/tests/test_api.py#L324) `test_dms_folders_trash_favorites_revision_restore_diff`.

## AC-017 — Администрирование и сессии

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When изменить пользователя с expected_updated_at / отозвать сессии. Then блокировка действует на следующем запросе; password_hash не отдаётся.

Negative: Given тот же actor и нарушенное условие (403 forbidden; 409 stale_record/self_admin_change). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When пользователь отзывает собственные сессии; ADMIN — сессии другого. Then сохраняются ограничения версии, владения и аудита.

Доказательство: [apps/api/tests/test_api.py:724](../../apps/api/tests/test_api.py#L724) `test_session_inventory_scoping_revocation_and_admin`.

## AC-018 — RU/EN и безопасная адаптация UI

Given ACTIVE сессия; назначение/допуск или административное permission согласно ACL. When выбрать язык / открыть задачи. Then переводы и права сервера определяют интерфейс.

Negative: Given тот же actor и нарушенное условие (Сетевой/5xx исход сохраняет UUID; после 401 интерфейс завершает сессию). When операция выполняется. Then сервер возвращает соответствующую ошибку и не выполняет запрещённый переход/чтение.

Alternative: Given условия альтернативы. When access_required не раскрывает title; completed ведёт в receipt. Then сохраняются ограничения версии, владения и аудита.

Доказательство: Missing Test для полного GWT сценария; UI unit checks не заменяют browser UAT.

## AC-N01 — граница времени

Given RESTRICTED grant ACTIVE, expires_at равен времени сервера. When выполняется file request. Then доступ уже запрещён; право действует только при expires_at > now. Проверка: [apps/api/tests/test_acl_live.py:26](../../apps/api/tests/test_acl_live.py#L26) `test_restricted_duration_boundaries`.

## AC-N02 — параллельные подтверждения

Given один grant PENDING и два независимых offices. When обе операции endorse выполняются одновременно. Then один grant активирован, по одному голосу каждого office, без двойной активации. Проверка: [apps/api/tests/test_acl_live.py:61](../../apps/api/tests/test_acl_live.py#L61) `test_parallel_independent_votes_activate_exactly_once`.

## AC-N03 — ошибки хранения

Given файл отсутствует или checksum не совпадает. When допущенный пользователь скачивает версию. Then 503 file_unavailable и байты не выдаются. Проверка: [apps/api/tests/test_api.py:662](../../apps/api/tests/test_api.py#L662) `test_scan_quarantine_fail_closed_attestation_and_legacy_download`.
