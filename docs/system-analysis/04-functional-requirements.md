# Functional Requirements

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Все FR ниже восстановлены из реализации. Наличие теста — отдельный факт от его запуска; свежие результаты указаны в отчёте.

## FR-001 — Регистрация документа

Описание: Создать карточку с title, type_id и валидными метаданными. Actor: владелец.

- Preconditions: ACTIVE сессия и существующий document type.
- Trigger: `POST /api/v1/documents`.
- Main Flow: Сервер назначает owner/department, sequence даёт номер, аудит и результат ключа коммитятся вместе.
- Alternative Flow: Можно создать карточку без файла; на отправке файл обязателен.
- Exception Flow: 422 invalid_document_type; одинаковый ключ с другим телом → 409.
- Postconditions: Создана карточка DRAFT с revision=1.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-001 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## FR-002 — Редактирование и конкуренция

Описание: Отправить PATCH с expected_revision. Actor: владелец.

- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Trigger: `PATCH /api/v1/documents/{doc_id}`.
- Main Flow: Блокировка карточки; сверка revision; изменение только переданных полей; аудит.
- Alternative Flow: Непереданные поля сохраняются; nullable custom field можно очистить null.
- Exception Flow: 409 stale_document; null title → 422; RESTRICTED downgrade → 403.
- Postconditions: Revision увеличена; старые версии не переписаны.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-002 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## FR-003 — Файлы и версии

Описание: Передать multipart file и change_note. Actor: владелец.

- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Trigger: `POST /api/v1/documents/{doc_id}/versions`.
- Main Flow: Хеш, формат, quarantine, scanner, promote, номер версии под блокировкой, commit.
- Alternative Flow: После неизвестного ответа повтор с тем же ключом возвращает ту же версию.
- Exception Flow: 413 размер; 422 malware_detected; 503 scanner_unavailable.
- Postconditions: Immutable версия и current_version_id; scanner attestation в production.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-003 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## FR-004 — Приватное чтение файла

Описание: Скачать конкретную версию. Actor: допущенный пользователь.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `GET /api/v1/documents/{doc_id}/versions/{version_id}/download`.
- Main Flow: ACL file → запись версии → scan attestation → сверка SHA/размера → аудит → stream.
- Alternative Flow: Owner видит свои старые версии; остальные только разрешённые.
- Exception Flow: 404 скрывает существование; 503 file_unavailable.
- Postconditions: Скачаны только разрешённые байты.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-004 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## FR-005 — Списки, поиск, dashboard

Описание: Запросить список / поиск. Actor: ACTIVE пользователь.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `GET /api/v1/documents`.
- Main Flow: SQL ACL, frozen title/status, фильтры, count и offset page.
- Alternative Flow: my/favorites/archive/trash; dashboard по доступным карточкам.
- Exception Flow: 401 неактивная сессия; 422 неверный page/page_size.
- Postconditions: Чужие недоступные карточки не возвращены.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-005 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## FR-006 — Запуск согласования

Описание: Выбрать template_id, expected_revision и UUID в body. Actor: владелец.

- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Trigger: `POST /api/v1/documents/{doc_id}/workflows`.
- Main Flow: Блокировка; файл и scan; required route; snapshot; план ACTIVE лиц кроме owner; первый этап PENDING.
- Alternative Flow: Условные этапы допустимы для необязательного маршрута; optional submit даёт SUBMITTED.
- Exception Flow: 409 required_workflow/stale_document; 422 invalid_workflow_target.
- Postconditions: IN_APPROVAL; версия, шаблон и план закреплены.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-006 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/workflows.py](../../apps/api/app/workflows.py).

## FR-007 — Решение и единогласие

Описание: action=approve и idempotency_key. Actor: текущий назначенный участник.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/workflows/{instance_id}/decisions`.
- Main Flow: Проверки этапа, роли, версии и card/file; решение; следующий этап после всех; receipt и аудит.
- Alternative Flow: При последнем этапе документ APPROVED; тот же ключ возвращает собственную квитанцию.
- Exception Flow: 404 чужое назначение; 403 access_required; 409 workflow_scope_changed.
- Postconditions: Личное решение записано один раз; доступ участника прекращён.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-007 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/workflows.py](../../apps/api/app/workflows.py).

## FR-008 — Возврат, отклонение, отмена

Описание: action=revision/reject/cancel с комментарием. Actor: участник / владелец для cancel.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/workflows/{instance_id}/decisions`.
- Main Flow: Терминальный исход процесса, отмена ожидающих задач, отзыв review grants.
- Alternative Flow: REVISION_REQUIRED позволяет редактирование и новый процесс; REJECTED не имеет пути прямого resubmit.
- Exception Flow: 422 approval_comment_required; 409 invalid_transition.
- Postconditions: История прежнего процесса сохранена.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-008 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/workflows.py](../../apps/api/app/workflows.py).

## FR-009 — Шаблоны и обязательный маршрут

Описание: Создать новую версию маршрута; оператор отдельно задаёт type policy. Actor: ADMIN / оператор для requirements.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/workflow-templates`.
- Main Flow: Проверить selectors/stages; новая immutable template version; type → точный template.
- Alternative Flow: Без requirement владелец выбирает template; условия не допускаются в required route.
- Exception Flow: 422 unauthorized_reviewer; 409 required_stage_condition.
- Postconditions: Старые instances остаются на прежнем шаблоне.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-009 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Partially implemented.
- Code References: [apps/api/app/workflows.py](../../apps/api/app/workflows.py).

## FR-010 — Персональный временный допуск

Описание: Задать лицо, version_id, actions, purpose, reason, hours. Actor: owner / CUSTODIAN.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/documents/{doc_id}/access-requests`.
- Main Flow: Фиксируется recipient role/dept, classification, scope_hash, snapshot; owner nonrestricted активирует.
- Alternative Flow: CUSTODIAN request требует подтверждение; grants не переходят на новую версию.
- Exception Flow: 422 invalid_grant_target/duration; trash → 409.
- Postconditions: Допуск привязан к версии и проверяется на каждом запросе.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-010 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/access.py](../../apps/api/app/access.py).

## FR-011 — Два одобрения RESTRICTED

Описание: Подтвердить office и scope_hash. Actor: независимые CUSTODIAN и SECURITY.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/access/grants/{grant_id}/endorse`.
- Main Flow: Проверить полномочие, independence, scope, deadline; второй голос активирует.
- Alternative Flow: Первый голос оставляет PENDING; срок ≤8 часов от активации.
- Exception Flow: 403 self_approval_forbidden; 409 duplicate_endorsement/grant_scope_changed.
- Postconditions: ACTIVE только после двух разных лиц.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-011 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/access.py](../../apps/api/app/access.py).

## FR-012 — Срок и отзыв допуска

Описание: Отозвать с reason либо достичь expires_at. Actor: доступный участник grant / authority.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/access/grants/{grant_id}/revoke`.
- Main Flow: ACL сразу отвергает истёкший/отозванный scope; API меняет ACTIVE→REVOKED/PENDING→DENIED.
- Alternative Flow: Повтор terminal revoke не добавляет повторный аудит; GET grants материализует EXPIRED до 100 строк.
- Exception Flow: 404 чужой grant; изменение роли/отдела лишает допуска.
- Postconditions: Новые чтения и скачивания запрещены.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-012 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/access.py](../../apps/api/app/access.py).

## FR-013 — Черновики MANAGER

Описание: Передать текущую версию отдела на review. Actor: владелец + CUSTODIAN policy.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/documents/{doc_id}/department-review`.
- Main Flow: Проверить enabled, DRAFT/REVISION_REQUIRED, PUBLIC/INTERNAL; создать персональные grants текущим MANAGER.
- Alternative Flow: APPROVED PUBLIC/INTERNAL доступен MANAGER своего отдела без draft handoff.
- Exception Flow: 409 department_review_disabled; 422 invalid_grant_target.
- Postconditions: Новые managers/версии не наследуют старый допуск.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-013 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/access.py](../../apps/api/app/access.py).

## FR-014 — Квитанции и снимок проверки

Описание: Открыть собственную завершённую задачу. Actor: автор собственного решения.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `GET /api/v1/approvals/{approval_id}/receipt`.
- Main Flow: Вернуть исход, дату, opaque ids, can_download=false; snapshot только при отдельном условии.
- Alternative Flow: Nonrestricted snapshot <7 дней пока процесс RUNNING; иначе нужен snapshot grant; restricted всегда отдельный допуск.
- Exception Flow: 404 чужая/скрытая квитанция; revoked snapshot исключён.
- Postconditions: Нет файла, актуальной карточки или чужих комментариев.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-014 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/access.py](../../apps/api/app/access.py).

## FR-015 — Комментарии и история

Описание: Оставить комментарий или запросить разрешённый раздел. Actor: owner / текущий участник / отдельный grant.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `POST /api/v1/documents/{doc_id}/comments`.
- Main Flow: Сервер связывает комментарий с версией/этапом; история требует history action.
- Alternative Flow: Owner видит весь поток; участник только свой текущий scope; карточка не даёт историю.
- Exception Flow: 404 нет доступа; 409 document_not_editable для archive/trash.
- Postconditions: Содержимое и аудит не раскрывают другие scopes.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-015 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## FR-016 — Папки, корзина, восстановление

Описание: Изменить организацию или восстановить версию с expected_revision. Actor: владелец.

- Preconditions: ACTIVE сессия; документ принадлежит actor; для изменения — DRAFT/REVISION_REQUIRED и не trash.
- Trigger: `POST /api/v1/documents/{doc_id}/versions/{version_id}/restore`.
- Main Flow: Личное дерево, защита цикла/depth; корзина soft delete; восстановление версии через storage в новый blob.
- Alternative Flow: Favorites PUT/DELETE идемпотентны; TXT diff требует file+compare обеих версий.
- Exception Flow: 409 folder_cycle/stale_document; 422 diff_unsupported.
- Postconditions: Исходные версии и аудит сохранены.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-016 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/dms.py](../../apps/api/app/dms.py).

## FR-017 — Администрирование и сессии

Описание: Изменить пользователя с expected_updated_at / отозвать сессии. Actor: ADMIN / пользователь для своих сессий.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `PATCH /api/v1/users/{user_id}`.
- Main Flow: Проверить ADMIN, self_admin_change и CAS; role/status/department только сервером.
- Alternative Flow: Пользователь отзывает собственные сессии; ADMIN — сессии другого.
- Exception Flow: 403 forbidden; 409 stale_record/self_admin_change.
- Postconditions: Блокировка действует на следующем запросе; password_hash не отдаётся.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-017 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Implemented.
- Code References: [apps/api/app/catalog.py](../../apps/api/app/catalog.py).

## FR-018 — RU/EN и безопасная адаптация UI

Описание: Выбрать язык / открыть задачи. Actor: пользователь.

- Preconditions: ACTIVE сессия; назначение/допуск или административное permission согласно ACL.
- Trigger: `GET /api/v1/approvals`.
- Main Flow: RU по умолчанию, localStorage; capabilities и task kind определяют загружаемые разделы.
- Alternative Flow: access_required не раскрывает title; completed ведёт в receipt.
- Exception Flow: Сетевой/5xx исход сохраняет UUID; после 401 интерфейс завершает сессию.
- Postconditions: Переводы и права сервера определяют интерфейс.
- Business Rules: сервер определяет личность, право и scope; см. [ACL](13-security-and-access.md), [процессы](06-business-processes.md) и контракт соответствующей операции.
- Acceptance Criteria: AC-018 и negative criterion в [критериях](15-acceptance-criteria.md).
- Implementation Status: Partially implemented.
- Code References: [apps/api/app/workflows.py](../../apps/api/app/workflows.py).
