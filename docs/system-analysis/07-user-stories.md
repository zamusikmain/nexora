# User Stories

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

## US-001 — Регистрация документа

Как владелец, я хочу создать карточку с title, type_id и валидными метаданными, чтобы получить результат: создана карточка DRAFT с revision=1.

- Business Value: Уникальный номер, автор и проверенные поля.
- Priority: P1.
- Preconditions: ACTIVE сессия и существующий document type.
- Main Scenario: Сервер назначает owner/department, sequence даёт номер, аудит и результат ключа коммитятся вместе.
- Alternative Scenario: Можно создать карточку без файла; на отправке файл обязателен.
- Negative Scenario: 422 invalid_document_type; одинаковый ключ с другим телом → 409.
- Acceptance Criteria: AC-001, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-001; BR-001.
- Implementation Status: Implemented.

## US-002 — Редактирование и конкуренция

Как владелец, я хочу отправить PATCH с expected_revision, чтобы получить результат: revision увеличена; старые версии не переписаны.

- Business Value: Уникальный номер, автор и проверенные поля.
- Priority: P1.
- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Main Scenario: Блокировка карточки; сверка revision; изменение только переданных полей; аудит.
- Alternative Scenario: Непереданные поля сохраняются; nullable custom field можно очистить null.
- Negative Scenario: 409 stale_document; null title → 422; RESTRICTED downgrade → 403.
- Acceptance Criteria: AC-002, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-002; BR-001.
- Implementation Status: Implemented.

## US-003 — Файлы и версии

Как владелец, я хочу передать multipart file и change_note, чтобы получить результат: immutable версия и current_version_id; scanner attestation в production.

- Business Value: Работа с проверенным файлом и сохранение старых байтов.
- Priority: P0.
- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Main Scenario: Хеш, формат, quarantine, scanner, promote, номер версии под блокировкой, commit.
- Alternative Scenario: После неизвестного ответа повтор с тем же ключом возвращает ту же версию.
- Negative Scenario: 413 размер; 422 malware_detected; 503 scanner_unavailable.
- Acceptance Criteria: AC-003, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-003; BR-002.
- Implementation Status: Implemented.

## US-004 — Приватное чтение файла

Как допущенный пользователь, я хочу скачать конкретную версию, чтобы получить результат: скачаны только разрешённые байты.

- Business Value: Работа с проверенным файлом и сохранение старых байтов.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: ACL file → запись версии → scan attestation → сверка SHA/размера → аудит → stream.
- Alternative Scenario: Owner видит свои старые версии; остальные только разрешённые.
- Negative Scenario: 404 скрывает существование; 503 file_unavailable.
- Acceptance Criteria: AC-004, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-004; BR-002.
- Implementation Status: Implemented.

## US-005 — Списки, поиск, dashboard

Как ACTIVE пользователь, я хочу запросить список / поиск, чтобы получить результат: чужие недоступные карточки не возвращены.

- Business Value: Найти разрешённые документы без раскрытия чужих.
- Priority: P1.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: SQL ACL, frozen title/status, фильтры, count и offset page.
- Alternative Scenario: my/favorites/archive/trash; dashboard по доступным карточкам.
- Negative Scenario: 401 неактивная сессия; 422 неверный page/page_size.
- Acceptance Criteria: AC-005, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-005; BR-003.
- Implementation Status: Implemented.

## US-006 — Запуск согласования

Как владелец, я хочу выбрать template_id, expected_revision и UUID в body, чтобы получить результат: iN_APPROVAL; версия, шаблон и план закреплены.

- Business Value: Проверять одну закреплённую версию по маршруту.
- Priority: P0.
- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Main Scenario: Блокировка; файл и scan; required route; snapshot; план ACTIVE лиц кроме owner; первый этап PENDING.
- Alternative Scenario: Условные этапы допустимы для необязательного маршрута; optional submit даёт SUBMITTED.
- Negative Scenario: 409 required_workflow/stale_document; 422 invalid_workflow_target.
- Acceptance Criteria: AC-006, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-006; BR-004.
- Implementation Status: Implemented.

## US-007 — Решение и единогласие

Как текущий назначенный участник, я хочу action=approve и idempotency_key, чтобы получить результат: личное решение записано один раз; доступ участника прекращён.

- Business Value: Проверять одну закреплённую версию по маршруту.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Проверки этапа, роли, версии и card/file; решение; следующий этап после всех; receipt и аудит.
- Alternative Scenario: При последнем этапе документ APPROVED; тот же ключ возвращает собственную квитанцию.
- Negative Scenario: 404 чужое назначение; 403 access_required; 409 workflow_scope_changed.
- Acceptance Criteria: AC-007, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-007; BR-004.
- Implementation Status: Implemented.

## US-008 — Возврат, отклонение, отмена

Как участник / владелец для cancel, я хочу action=revision/reject/cancel с комментарием, чтобы получить результат: история прежнего процесса сохранена.

- Business Value: Проверять одну закреплённую версию по маршруту.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Терминальный исход процесса, отмена ожидающих задач, отзыв review grants.
- Alternative Scenario: REVISION_REQUIRED позволяет редактирование и новый процесс; REJECTED не имеет пути прямого resubmit.
- Negative Scenario: 422 approval_comment_required; 409 invalid_transition.
- Acceptance Criteria: AC-008, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-008; BR-004.
- Implementation Status: Implemented.

## US-009 — Шаблоны и обязательный маршрут

Как ADMIN / оператор для requirements, я хочу создать новую версию маршрута; оператор отдельно задаёт type policy, чтобы получить результат: старые instances остаются на прежнем шаблоне.

- Business Value: Проверять одну закреплённую версию по маршруту.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Проверить selectors/stages; новая immutable template version; type → точный template.
- Alternative Scenario: Без requirement владелец выбирает template; условия не допускаются в required route.
- Negative Scenario: 422 unauthorized_reviewer; 409 required_stage_condition.
- Acceptance Criteria: AC-009, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-009; BR-004.
- Implementation Status: Partially implemented.

## US-010 — Персональный временный допуск

Как owner / CUSTODIAN, я хочу задать лицо, version_id, actions, purpose, reason, hours, чтобы получить результат: допуск привязан к версии и проверяется на каждом запросе.

- Business Value: Выдавать доступ по необходимости и сроку.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Фиксируется recipient role/dept, classification, scope_hash, snapshot; owner nonrestricted активирует.
- Alternative Scenario: CUSTODIAN request требует подтверждение; grants не переходят на новую версию.
- Negative Scenario: 422 invalid_grant_target/duration; trash → 409.
- Acceptance Criteria: AC-010, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-010; BR-005.
- Implementation Status: Implemented.

## US-011 — Два одобрения RESTRICTED

Как независимые CUSTODIAN и SECURITY, я хочу подтвердить office и scope_hash, чтобы получить результат: aCTIVE только после двух разных лиц.

- Business Value: Выдавать доступ по необходимости и сроку.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Проверить полномочие, independence, scope, deadline; второй голос активирует.
- Alternative Scenario: Первый голос оставляет PENDING; срок ≤8 часов от активации.
- Negative Scenario: 403 self_approval_forbidden; 409 duplicate_endorsement/grant_scope_changed.
- Acceptance Criteria: AC-011, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-011; BR-005.
- Implementation Status: Implemented.

## US-012 — Срок и отзыв допуска

Как доступный участник grant / authority, я хочу отозвать с reason либо достичь expires_at, чтобы получить результат: новые чтения и скачивания запрещены.

- Business Value: Выдавать доступ по необходимости и сроку.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: ACL сразу отвергает истёкший/отозванный scope; API меняет ACTIVE→REVOKED/PENDING→DENIED.
- Alternative Scenario: Повтор terminal revoke не добавляет повторный аудит; GET grants материализует EXPIRED до 100 строк.
- Negative Scenario: 404 чужой grant; изменение роли/отдела лишает допуска.
- Acceptance Criteria: AC-012, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-012; BR-005.
- Implementation Status: Implemented.

## US-013 — Черновики MANAGER

Как владелец + CUSTODIAN policy, я хочу передать текущую версию отдела на review, чтобы получить результат: новые managers/версии не наследуют старый допуск.

- Business Value: Выдавать доступ по необходимости и сроку.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Проверить enabled, DRAFT/REVISION_REQUIRED, PUBLIC/INTERNAL; создать персональные grants текущим MANAGER.
- Alternative Scenario: APPROVED PUBLIC/INTERNAL доступен MANAGER своего отдела без draft handoff.
- Negative Scenario: 409 department_review_disabled; 422 invalid_grant_target.
- Acceptance Criteria: AC-013, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-013; BR-005.
- Implementation Status: Implemented.

## US-014 — Квитанции и снимок проверки

Как автор собственного решения, я хочу открыть собственную завершённую задачу, чтобы получить результат: нет файла, актуальной карточки или чужих комментариев.

- Business Value: Выдавать доступ по необходимости и сроку.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Вернуть исход, дату, opaque ids, can_download=false; snapshot только при отдельном условии.
- Alternative Scenario: Nonrestricted snapshot <7 дней пока процесс RUNNING; иначе нужен snapshot grant; restricted всегда отдельный допуск.
- Negative Scenario: 404 чужая/скрытая квитанция; revoked snapshot исключён.
- Acceptance Criteria: AC-014, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-014; BR-005.
- Implementation Status: Implemented.

## US-015 — Комментарии и история

Как owner / текущий участник / отдельный grant, я хочу оставить комментарий или запросить разрешённый раздел, чтобы получить результат: содержимое и аудит не раскрывают другие scopes.

- Business Value: Сохранять действия с ограничением чтения.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Сервер связывает комментарий с версией/этапом; история требует history action.
- Alternative Scenario: Owner видит весь поток; участник только свой текущий scope; карточка не даёт историю.
- Negative Scenario: 404 нет доступа; 409 document_not_editable для archive/trash.
- Acceptance Criteria: AC-015, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-015; BR-006.
- Implementation Status: Implemented.

## US-016 — Папки, корзина, восстановление

Как владелец, я хочу изменить организацию или восстановить версию с expected_revision, чтобы получить результат: исходные версии и аудит сохранены.

- Business Value: Работа с проверенным файлом и сохранение старых байтов.
- Priority: P0.
- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Main Scenario: Личное дерево, защита цикла/depth; корзина soft delete; восстановление версии через storage в новый blob.
- Alternative Scenario: Favorites PUT/DELETE идемпотентны; TXT diff требует file+compare обеих версий.
- Negative Scenario: 409 folder_cycle/stale_document; 422 diff_unsupported.
- Acceptance Criteria: AC-016, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-016; BR-002.
- Implementation Status: Implemented.

## US-017 — Администрирование и сессии

Как ADMIN / пользователь для своих сессий, я хочу изменить пользователя с expected_updated_at / отозвать сессии, чтобы получить результат: блокировка действует на следующем запросе; password_hash не отдаётся.

- Business Value: Управлять аккаунтами и инфраструктурой раздельно.
- Priority: P0.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: Проверить ADMIN, self_admin_change и CAS; role/status/department только сервером.
- Alternative Scenario: Пользователь отзывает собственные сессии; ADMIN — сессии другого.
- Negative Scenario: 403 forbidden; 409 stale_record/self_admin_change.
- Acceptance Criteria: AC-017, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-017; BR-007.
- Implementation Status: Implemented.

## US-018 — RU/EN и безопасная адаптация UI

Как пользователь, я хочу выбрать язык / открыть задачи, чтобы получить результат: переводы и права сервера определяют интерфейс.

- Business Value: Работать на RU/EN и понимать отсутствие допуска.
- Priority: P1.
- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Main Scenario: RU по умолчанию, localStorage; capabilities и task kind определяют загружаемые разделы.
- Alternative Scenario: access_required не раскрывает title; completed ведёт в receipt.
- Negative Scenario: Сетевой/5xx исход сохраняет UUID; после 401 интерфейс завершает сессию.
- Acceptance Criteria: AC-018, Given/When/Then в [общем каталоге](15-acceptance-criteria.md).
- Related FR: FR-018; BR-008.
- Implementation Status: Partially implemented.
