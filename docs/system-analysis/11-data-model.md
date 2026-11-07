# Data Model & Data Dictionary

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

24 прикладные таблицы, 195 полей. Типы ниже из SQLAlchemy metadata, nullable и defaults именно ORM/server defaults. Python default (`uid`, `dict`, `list`, `True` и т.п.) не означает DEFAULT в PostgreSQL. Constraints/indexes перечислены отдельно; FK target записан у поля. Служебная alembic_version управляет ревизией и не входит в ORM-24. Sequence document_number_seq не таблица.

[ERD](diagrams/data-model.mmd), [машинный metadata snapshot](data-model.json). Прямого сравнения с рабочей БД не выполнялось: расхождение deployed schema Unknown. Миграции 0007/0008 добавляют ACL/snapshots и operation_keys/workflow_requirements; это не доказательство применения.

## Основные связи

Document → owner/User, Department, Type, Folder; версии принадлежат document. current_version composite FK не позволяет версию чужого документа. WorkflowInstance закрепляет document_version и template; Approvals задают лиц и этапы, WorkflowEvent фиксирует действия. AccessGrant привязывает recipient и version, GrantEndorsement — office vote; ReviewReceipt соответствует одному Approval. Отдельные AuthSession и LoginThrottle не содержат document ACL. AuditEvent.target_id — polymorphic ссылка без общего FK.

## Ограничения сверх ORM

Immutable triggers: версии, аудит, templates, workflow_events, endorsements, receipts/revocations и operation_keys; workflow snapshot и grant scope защищены отдельными triggers. Это поведение миграций, не SQLAlchemy column property. Документный номер sequence может иметь пропуски. Наличие ON UPDATE Python func.now не означает PG trigger timestamp. SQL-предикаты ACL — application-level, не PostgreSQL RLS.

Источники: [apps/api/app/models.py](../../apps/api/app/models.py), [apps/api/migrations/versions/0001_core.py](../../apps/api/migrations/versions/0001_core.py), [apps/api/migrations/versions/0004_workflows.py](../../apps/api/migrations/versions/0004_workflows.py), [apps/api/migrations/versions/0007_acl.py](../../apps/api/migrations/versions/0007_acl.py), [apps/api/migrations/versions/0008_hardening.py](../../apps/api/migrations/versions/0008_hardening.py).

## access_grants

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `document_id` | VARCHAR(36) | Нет | `—` | Документ, которому принадлежит версия/процесс/допуск | FK document_versions.document_id,documents.id |
| `version_id` | VARCHAR(36) | Нет | `—` | Конкретная версия файла, закреплённая для ресурса | FK document_versions.id |
| `recipient_id` | VARCHAR(36) | Нет | `—` | Персональный получатель допуска | FK users.id |
| `requested_by` | VARCHAR(36) | Нет | `—` | Инициатор запроса допуска | FK users.id |
| `recipient_role` | VARCHAR(20) | Нет | `—` | Роль recipient в момент request; должна совпадать при чтении | — |
| `recipient_department_id` | VARCHAR(36) | Да | `—` | Отдел recipient в момент request; проверяется повторно | — |
| `department_id` | VARCHAR(36) | Да | `—` | Отдел пользователя/документа/office; у grant — зафиксированный scope | — |
| `classification` | VARCHAR(20) | Нет | `—` | Классификация, закреплённая при grant request | — |
| `purpose` | VARCHAR(20) | Нет | `—` | Цель grant: personal/review/draft/audit_snapshot/incident | — |
| `instance_id` | VARCHAR(36) | Да | `—` | Экземпляр согласования | FK workflow_instances.id |
| `approval_id` | VARCHAR(36) | Да | `—` | Назначение согласования и ключ собственной receipt/revocation | FK approvals.id |
| `can_card` | BOOLEAN | Нет | `False` (python) | Разрешение действия card для конкретного grant scope | — |
| `can_file` | BOOLEAN | Нет | `False` (python) | Разрешение действия file для конкретного grant scope | — |
| `can_snapshot` | BOOLEAN | Нет | `False` (python) | Разрешение действия snapshot для конкретного grant scope | — |
| `can_comments` | BOOLEAN | Нет | `False` (python) | Разрешение действия comments для конкретного grant scope | — |
| `can_history` | BOOLEAN | Нет | `False` (python) | Разрешение действия history для конкретного grant scope | — |
| `can_compare` | BOOLEAN | Нет | `False` (python) | Разрешение действия compare для конкретного grant scope | — |
| `reason` | VARCHAR(1000) | Нет | `—` | Обоснование grant/revoke | — |
| `duration_hours` | INTEGER | Нет | `—` | Длительность после активации | — |
| `scope_hash` | VARCHAR(64) | Нет | `—` | Хеш неизменного scope, подтверждаемый offices | — |
| `status` | VARCHAR(20) | Нет | `PENDING` (python) | Текущее состояние сущности; допустимые значения в CHECK/серверных правилах | — |
| `requested_at` | DATETIME | Нет | `—` | Время request | — |
| `review_deadline` | DATETIME | Нет | `—` | Конец 24-часового окна подтверждения | — |
| `activated_at` | DATETIME | Да | `—` | Момент активации | — |
| `expires_at` | DATETIME | Да | `—` | Конец действительности сессии/полномочия/допуска | — |
| `revoked_at` | DATETIME | Да | `—` | Момент отзыва | — |
| `snapshot` | JSON | Да | `—` | Разрешённый замороженный контекст grant/receipt; не файл | — |

Constraints:

- `grant_duration` CheckConstraint () — `duration_hours > 0 AND duration_hours <= 168`
- `grant_purpose` CheckConstraint () — `purpose IN ('personal','review','audit_snapshot','draft','incident')`
- `grant_status` CheckConstraint () — `status IN ('PENDING','ACTIVE','DENIED','REVOKED','EXPIRED')`
- `(unnamed)` ForeignKeyConstraint (instance_id)
- `(unnamed)` ForeignKeyConstraint (recipient_id)
- `(unnamed)` ForeignKeyConstraint (approval_id)
- `(unnamed)` ForeignKeyConstraint (requested_by)
- `(unnamed)` ForeignKeyConstraint (document_id)
- `fk_grant_version` ForeignKeyConstraint (document_id, version_id)
- `(unnamed)` PrimaryKeyConstraint (id)

Indexes:

- `ix_grants_recipient_document` (recipient_id, document_id, status, expires_at), unique=False

## acl_authorities

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `user_id` | VARCHAR(36) | Нет | `—` | Связь с users.id | FK users.id |
| `department_id` | VARCHAR(36) | Нет | `—` | Отдел пользователя/документа/office; у grant — зафиксированный scope | FK departments.id |
| `office` | VARCHAR(20) | Нет | `—` | Полномочие CUSTODIAN/SECURITY, не user.role | — |
| `active` | BOOLEAN | Нет | `True` (python) | Флаг включённого полномочия | — |
| `expires_at` | DATETIME | Нет | `—` | Конец действительности сессии/полномочия/допуска | — |

Constraints:

- `acl_authority_office` CheckConstraint () — `office IN ('CUSTODIAN','SECURITY')`
- `(unnamed)` ForeignKeyConstraint (department_id)
- `(unnamed)` ForeignKeyConstraint (user_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `uq_acl_authority` UniqueConstraint (user_id, department_id, office)

Indexes:

- `ix_acl_authorities_user_id` (user_id), unique=False

## acl_department_policies

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `department_id` | VARCHAR(36) | Нет | `—` | Отдел пользователя/документа/office; у grant — зафиксированный scope | PK; FK departments.id |
| `enabled` | BOOLEAN | Нет | `False` (python) | Включение opt-in department review | — |
| `updated_by` | VARCHAR(36) | Нет | `—` | Автор изменения department policy | FK users.id |
| `updated_at` | DATETIME | Нет | `—` | Время изменения; CAS token где применяется | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (updated_by)
- `(unnamed)` ForeignKeyConstraint (department_id)
- `(unnamed)` PrimaryKeyConstraint (department_id)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## approvals

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `instance_id` | VARCHAR(36) | Нет | `—` | Экземпляр согласования | FK workflow_instances.id |
| `stage` | INTEGER | Нет | `—` | Индекс этапа процесса/назначения/комментария | — |
| `user_id` | VARCHAR(36) | Нет | `—` | Связь с users.id | FK users.id |
| `status` | VARCHAR(30) | Нет | `—` | Текущее состояние сущности; допустимые значения в CHECK/серверных правилах | — |
| `due_at` | DATETIME | Да | `—` | Срок текущего назначения, без автоматической эскалации | — |
| `acted_at` | DATETIME | Да | `—` | Время личного решения | — |

Constraints:

- `approval_status` CheckConstraint () — `status IN ('WAITING','PENDING','APPROVED','REJECTED','REVISION_REQUIRED','CANCELLED')`
- `(unnamed)` ForeignKeyConstraint (instance_id)
- `(unnamed)` ForeignKeyConstraint (user_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `uq_approval_assignee` UniqueConstraint (instance_id, stage, user_id)

Indexes:

- `ix_approvals_instance_id` (instance_id), unique=False
- `ix_approvals_user_status_due` (user_id, status, due_at), unique=False

## audit_events

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `actor_id` | VARCHAR(36) | Да | `—` | Пользователь, выполнивший действие; nullable для системного аудита | FK users.id |
| `action` | VARCHAR(60) | Нет | `—` | Тип аудируемого/процессного действия | — |
| `target_type` | VARCHAR(30) | Нет | `—` | Тип объекта аудита | — |
| `target_id` | VARCHAR(36) | Да | `—` | Идентификатор объекта аудита; polymorphic, не общий FK | — |
| `safe_metadata` | JSON | Нет | `dict` (python) | Ограниченные служебные данные аудита | — |
| `request_id` | VARCHAR(36) | Нет | `—` | Корреляционный UUID HTTP/операторской операции | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (actor_id)
- `(unnamed)` PrimaryKeyConstraint (id)

Indexes:

- `ix_audit_events_action` (action), unique=False
- `ix_audit_events_created_at` (created_at), unique=False
- `ix_audit_events_target_id` (target_id), unique=False

## auth_sessions

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `public_id` | VARCHAR(36) | Нет | `uid` (python) | Публичный идентификатор сессии для безопасного отзыва | — |
| `user_agent` | VARCHAR(200) | Нет | `` (server) | Очищенное описание клиента сессии | — |
| `id` | VARCHAR(64) | Нет | `—` | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `user_id` | VARCHAR(36) | Нет | `—` | Связь с users.id | FK users.id |
| `csrf_token` | VARCHAR(64) | Нет | `—` | Session CSRF token; сверяется при mutation | — |
| `expires_at` | DATETIME | Нет | `—` | Конец действительности сессии/полномочия/допуска | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (user_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `uq_auth_session_public_id` UniqueConstraint (public_id)

Indexes:

- `ix_auth_sessions_expires_at` (expires_at), unique=False
- `ix_auth_sessions_user_id` (user_id), unique=False

## comments

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `document_id` | VARCHAR(36) | Нет | `—` | Документ, которому принадлежит версия/процесс/допуск | FK documents.id |
| `author_id` | VARCHAR(36) | Нет | `—` | Автор комментария | FK users.id |
| `body` | VARCHAR(4000) | Нет | `—` | Текст комментария | — |
| `version_id` | VARCHAR(36) | Да | `—` | Конкретная версия файла, закреплённая для ресурса | FK document_versions.id |
| `instance_id` | VARCHAR(36) | Да | `—` | Экземпляр согласования | FK workflow_instances.id |
| `stage` | INTEGER | Да | `—` | Индекс этапа процесса/назначения/комментария | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (version_id)
- `(unnamed)` ForeignKeyConstraint (document_id)
- `(unnamed)` ForeignKeyConstraint (instance_id)
- `(unnamed)` ForeignKeyConstraint (author_id)
- `(unnamed)` PrimaryKeyConstraint (id)

Indexes:

- `ix_comments_document_id` (document_id), unique=False

## departments

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `code` | VARCHAR(40) | Нет | `—` | Стабильный код справочника/маршрута | UNIQUE; — |
| `name_ru` | VARCHAR(100) | Нет | `—` | Русское имя | — |
| `name_en` | VARCHAR(100) | Нет | `—` | Английское имя | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |
| `updated_at` | DATETIME | Нет | `now()` (server) | Время изменения; CAS token где применяется | — |

Constraints:

- `(unnamed)` PrimaryKeyConstraint (id)
- `(unnamed)` UniqueConstraint (code)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## document_favorites

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `user_id` | VARCHAR(36) | Нет | `—` | Связь с users.id | PK; FK users.id |
| `document_id` | VARCHAR(36) | Нет | `—` | Документ, которому принадлежит версия/процесс/допуск | PK; FK documents.id |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (document_id)
- `(unnamed)` ForeignKeyConstraint (user_id)
- `(unnamed)` PrimaryKeyConstraint (user_id, document_id)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## document_types

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `code` | VARCHAR(40) | Нет | `—` | Стабильный код справочника/маршрута | UNIQUE; — |
| `name_ru` | VARCHAR(100) | Нет | `—` | Русское имя | — |
| `name_en` | VARCHAR(100) | Нет | `—` | Английское имя | — |
| `metadata_schema` | JSON | Нет | `dict` (python) | Определение custom fields типа документа | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |
| `updated_at` | DATETIME | Нет | `now()` (server) | Время изменения; CAS token где применяется | — |

Constraints:

- `(unnamed)` PrimaryKeyConstraint (id)
- `(unnamed)` UniqueConstraint (code)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## document_versions

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `document_id` | VARCHAR(36) | Нет | `—` | Документ, которому принадлежит версия/процесс/допуск | FK documents.id |
| `version_number` | INTEGER | Нет | `—` | Монотонный номер версии в документе | — |
| `original_filename` | VARCHAR(200) | Нет | `—` | Очищенное исходное имя для download | — |
| `storage_key` | VARCHAR(64) | Нет | `—` | Приватный UUID-ключ blob; не URL | UNIQUE; — |
| `mime_type` | VARCHAR(100) | Нет | `—` | Проверенный MIME | — |
| `size` | BIGINT | Нет | `—` | Размер файла в байтах | — |
| `sha256` | VARCHAR(64) | Нет | `—` | Контрольная сумма байтов | — |
| `created_by` | VARCHAR(36) | Нет | `—` | Автор создания | FK users.id |
| `change_note` | VARCHAR(1000) | Да | `—` | Пояснение новой версии | — |
| `metadata_snapshot` | JSON | Да | `—` | Замороженные метаданные версии/процесса, не live карточка | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `version_positive` CheckConstraint () — `version_number > 0 AND size > 0`
- `(unnamed)` ForeignKeyConstraint (document_id)
- `(unnamed)` ForeignKeyConstraint (created_by)
- `(unnamed)` PrimaryKeyConstraint (id)
- `(unnamed)` UniqueConstraint (storage_key)
- `uq_document_version_identity` UniqueConstraint (document_id, id)
- `uq_document_version_number` UniqueConstraint (document_id, version_number)

Indexes:

- `ix_document_versions_document_id` (document_id), unique=False

## documents

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; FK document_versions.document_id |
| `number` | VARCHAR(40) | Нет | `—` | Серверный регистрационный номер документа | UNIQUE; — |
| `title` | VARCHAR(240) | Нет | `—` | Заголовок карточки | — |
| `type_id` | VARCHAR(36) | Нет | `—` | Тип документа или ключ mandatory route policy | FK document_types.id |
| `owner_id` | VARCHAR(36) | Нет | `—` | Владелец документа или личной папки; основание owner ACL | FK users.id |
| `department_id` | VARCHAR(36) | Да | `—` | Отдел пользователя/документа/office; у grant — зафиксированный scope | FK departments.id |
| `status` | VARCHAR(30) | Нет | `DRAFT` (python) | Текущее состояние сущности; допустимые значения в CHECK/серверных правилах | — |
| `business_metadata` | JSON | Нет | `dict` (python) | Проверенные custom fields карточки | — |
| `current_version_id` | VARCHAR(36) | Да | `—` | Текущая версия именно этого документа | FK document_versions.id |
| `description` | VARCHAR(4000) | Нет | `` (server) | Описание документа | — |
| `category` | VARCHAR(100) | Нет | `` (server) | Категория | — |
| `tags` | JSON | Нет | `[]` (server) | Метки документа | — |
| `responsible_id` | VARCHAR(36) | Да | `—` | Ответственный сотрудник документа; не автоматическое право доступа | FK users.id |
| `confidentiality` | VARCHAR(20) | Нет | `INTERNAL` (server) | PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED | — |
| `effective_date` | DATE | Да | `—` | Дата начала действия документа | — |
| `expiration_date` | DATE | Да | `—` | Дата окончания действия документа | — |
| `folder_id` | VARCHAR(36) | Да | `—` | Личная папка документа | FK folders.id |
| `deleted_at` | DATETIME | Да | `—` | Soft-delete marker корзины | — |
| `revision` | INTEGER | Нет | `1` (server) | CAS revision карточки | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |
| `updated_at` | DATETIME | Нет | `now()` (server) | Время изменения; CAS token где применяется | — |

Constraints:

- `document_confidentiality` CheckConstraint () — `confidentiality IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')`
- `document_dates` CheckConstraint () — `effective_date IS NULL OR expiration_date IS NULL OR expiration_date >= effective_date`
- `document_status` CheckConstraint () — `status IN ('DRAFT','SUBMITTED','IN_REVIEW','IN_APPROVAL','REVISION_REQUIRED','APPROVED','REJECTED','CANCELLED','ARCHIVED')`
- `(unnamed)` ForeignKeyConstraint (owner_id)
- `(unnamed)` ForeignKeyConstraint (department_id)
- `(unnamed)` ForeignKeyConstraint (responsible_id)
- `(unnamed)` ForeignKeyConstraint (folder_id)
- `(unnamed)` ForeignKeyConstraint (type_id)
- `fk_document_current_version` ForeignKeyConstraint (id, current_version_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `(unnamed)` UniqueConstraint (number)

Indexes:

- `ix_documents_deleted_at` (deleted_at), unique=False
- `ix_documents_department_status` (department_id, status), unique=False
- `ix_documents_folder_id` (folder_id), unique=False
- `ix_documents_owner_id` (owner_id), unique=False
- `ix_documents_responsible_id` (responsible_id), unique=False
- `ix_documents_type_id` (type_id), unique=False

## file_scans

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `version_id` | VARCHAR(36) | Нет | `—` | Конкретная версия файла, закреплённая для ресурса | PK; FK document_versions.id |
| `sha256` | VARCHAR(64) | Нет | `—` | Контрольная сумма байтов | — |
| `engine` | VARCHAR(40) | Нет | `—` | Scanner engine attestation (clamav) | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (version_id)
- `(unnamed)` PrimaryKeyConstraint (version_id)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## folders

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `name` | VARCHAR(120) | Нет | `—` | Имя папки | — |
| `owner_id` | VARCHAR(36) | Нет | `—` | Владелец документа или личной папки; основание owner ACL | FK users.id |
| `parent_id` | VARCHAR(36) | Да | `—` | Родитель личной папки | FK folders.id |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |
| `updated_at` | DATETIME | Нет | `now()` (server) | Время изменения; CAS token где применяется | — |

Constraints:

- `folder_not_self` CheckConstraint () — `parent_id IS NULL OR parent_id <> id`
- `(unnamed)` ForeignKeyConstraint (parent_id)
- `(unnamed)` ForeignKeyConstraint (owner_id)
- `(unnamed)` PrimaryKeyConstraint (id)

Indexes:

- `ix_folders_owner_id` (owner_id), unique=False
- `ix_folders_parent_id` (parent_id), unique=False

## grant_endorsements

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `grant_id` | VARCHAR(36) | Нет | `—` | Запрос допуска, подтверждаемый office | FK access_grants.id |
| `actor_id` | VARCHAR(36) | Нет | `—` | Пользователь, выполнивший действие; nullable для системного аудита | FK users.id |
| `authority_id` | VARCHAR(36) | Нет | `—` | Office-полномочие, по которому дан независимый голос | FK acl_authorities.id |
| `office` | VARCHAR(20) | Нет | `—` | Полномочие CUSTODIAN/SECURITY, не user.role | — |
| `scope_hash` | VARCHAR(64) | Нет | `—` | Хеш неизменного scope, подтверждаемый offices | — |
| `approved_at` | DATETIME | Нет | `—` | Момент независимого office-подтверждения | — |

Constraints:

- `grant_office` CheckConstraint () — `office IN ('CUSTODIAN','SECURITY')`
- `(unnamed)` ForeignKeyConstraint (authority_id)
- `(unnamed)` ForeignKeyConstraint (grant_id)
- `(unnamed)` ForeignKeyConstraint (actor_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `uq_grant_actor` UniqueConstraint (grant_id, actor_id)
- `uq_grant_office` UniqueConstraint (grant_id, office)

Indexes:

- `ix_grant_endorsements_grant_id` (grant_id), unique=False

## login_throttles

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(64) | Нет | `—` | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `failures` | INTEGER | Нет | `0` (python) | Счётчик неуспешных входов bucket | — |
| `window_start` | DATETIME | Нет | `—` | Начало окна throttle | — |

Constraints:

- `(unnamed)` PrimaryKeyConstraint (id)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## operation_keys

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `actor_id` | VARCHAR(36) | Нет | `—` | Пользователь, выполнивший действие; nullable для системного аудита | PK; FK users.id |
| `key` | VARCHAR(36) | Нет | `—` | Actor-scoped UUID Idempotency-Key | PK; — |
| `fingerprint` | VARCHAR(64) | Нет | `—` | Хеш метода, пути и payload обычной операции | — |
| `response` | JSON | Нет | `—` | Сохранённый JSON результата для replay | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (actor_id)
- `(unnamed)` PrimaryKeyConstraint (actor_id, key)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## receipt_revocations

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `approval_id` | VARCHAR(36) | Нет | `—` | Назначение согласования и ключ собственной receipt/revocation | PK; FK approvals.id |
| `actor_id` | VARCHAR(36) | Нет | `—` | Пользователь, выполнивший действие; nullable для системного аудита | FK users.id |
| `reason` | VARCHAR(1000) | Нет | `—` | Обоснование grant/revoke | — |
| `hide_receipt` | BOOLEAN | Нет | `False` (python) | Отзыв видимости самой receipt, а не только snapshot | — |
| `revoked_at` | DATETIME | Нет | `—` | Момент отзыва | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (approval_id)
- `(unnamed)` ForeignKeyConstraint (actor_id)
- `(unnamed)` PrimaryKeyConstraint (approval_id)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## review_receipts

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `approval_id` | VARCHAR(36) | Нет | `—` | Назначение согласования и ключ собственной receipt/revocation | PK; FK approvals.id |
| `actor_id` | VARCHAR(36) | Нет | `—` | Пользователь, выполнивший действие; nullable для системного аудита | FK users.id |
| `version_id` | VARCHAR(36) | Нет | `—` | Конкретная версия файла, закреплённая для ресурса | FK document_versions.id |
| `outcome` | VARCHAR(30) | Нет | `—` | Личный исход решения | — |
| `process_status` | VARCHAR(30) | Нет | `—` | Состояние процесса в момент выдачи receipt | — |
| `idempotency_key` | VARCHAR(36) | Нет | `—` | Actor-scoped UUID операции workflow/receipt | — |
| `acted_at` | DATETIME | Нет | `—` | Время личного решения | — |
| `snapshot` | JSON | Да | `—` | Разрешённый замороженный контекст grant/receipt; не файл | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (version_id)
- `(unnamed)` ForeignKeyConstraint (approval_id)
- `(unnamed)` ForeignKeyConstraint (actor_id)
- `(unnamed)` PrimaryKeyConstraint (approval_id)
- `uq_receipt_request` UniqueConstraint (actor_id, idempotency_key)

Indexes:

- `ix_review_receipts_actor_id` (actor_id), unique=False

## users

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `email` | VARCHAR(254) | Нет | `—` | Логин пользователя | UNIQUE; — |
| `display_name` | VARCHAR(100) | Нет | `—` | Отображаемое имя | — |
| `password_hash` | VARCHAR(255) | Нет | `—` | Argon2id hash; не возвращается клиенту | — |
| `role` | VARCHAR(20) | Нет | `USER` (python) | Бизнес-роль пользователя | — |
| `status` | VARCHAR(20) | Нет | `ACTIVE` (python) | Текущее состояние сущности; допустимые значения в CHECK/серверных правилах | — |
| `department_id` | VARCHAR(36) | Да | `—` | Отдел пользователя/документа/office; у grant — зафиксированный scope | FK departments.id |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |
| `updated_at` | DATETIME | Нет | `now()` (server) | Время изменения; CAS token где применяется | — |

Constraints:

- `user_role` CheckConstraint () — `role IN ('USER','REVIEWER','APPROVER','LEGAL','MANAGER','ADMIN')`
- `user_status` CheckConstraint () — `status IN ('ACTIVE','BLOCKED','DISABLED')`
- `(unnamed)` ForeignKeyConstraint (department_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `(unnamed)` UniqueConstraint (email)

Indexes:

- `ix_users_department_id` (department_id), unique=False

## workflow_events

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `instance_id` | VARCHAR(36) | Нет | `—` | Экземпляр согласования | FK workflow_instances.id |
| `actor_id` | VARCHAR(36) | Нет | `—` | Пользователь, выполнивший действие; nullable для системного аудита | FK users.id |
| `action` | VARCHAR(30) | Нет | `—` | Тип аудируемого/процессного действия | — |
| `comment` | VARCHAR(2000) | Нет | `—` | Текст решения workflow event | — |
| `previous_state` | VARCHAR(30) | Нет | `—` | Предыдущее состояние процесса | — |
| `new_state` | VARCHAR(30) | Нет | `—` | Новое состояние процесса | — |
| `idempotency_key` | VARCHAR(36) | Нет | `—` | Actor-scoped UUID операции workflow/receipt | — |
| `request_hash` | VARCHAR(64) | Нет | `—` | Хеш аргументов workflow request | — |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (instance_id)
- `(unnamed)` ForeignKeyConstraint (actor_id)
- `(unnamed)` PrimaryKeyConstraint (id)
- `uq_workflow_actor_request` UniqueConstraint (actor_id, idempotency_key)

Indexes:

- `ix_workflow_events_instance_id` (instance_id), unique=False

## workflow_instances

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `document_id` | VARCHAR(36) | Нет | `—` | Документ, которому принадлежит версия/процесс/допуск | FK document_versions.document_id,documents.id |
| `document_version_id` | VARCHAR(36) | Нет | `—` | Связь с document_versions.id | FK document_versions.id |
| `template_id` | VARCHAR(36) | Нет | `—` | Точная immutable версия шаблона процесса | FK workflow_templates.id |
| `metadata_snapshot` | JSON | Нет | `—` | Замороженные метаданные версии/процесса, не live карточка | — |
| `stage` | INTEGER | Нет | `0` (python) | Индекс этапа процесса/назначения/комментария | — |
| `status` | VARCHAR(30) | Нет | `RUNNING` (python) | Текущее состояние сущности; допустимые значения в CHECK/серверных правилах | — |
| `started_by` | VARCHAR(36) | Нет | `—` | Инициатор процесса | FK users.id |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |
| `completed_at` | DATETIME | Да | `—` | Время завершения процесса | — |

Constraints:

- `workflow_status` CheckConstraint () — `status IN ('RUNNING','APPROVED','REJECTED','REVISION_REQUIRED','CANCELLED')`
- `(unnamed)` ForeignKeyConstraint (template_id)
- `(unnamed)` ForeignKeyConstraint (started_by)
- `(unnamed)` ForeignKeyConstraint (document_id)
- `fk_workflow_document_version` ForeignKeyConstraint (document_id, document_version_id)
- `(unnamed)` PrimaryKeyConstraint (id)

Indexes:

- `ix_workflow_instances_document_id` (document_id), unique=False
- `uq_workflow_active_document` (document_id), unique=True

## workflow_requirements

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `type_id` | VARCHAR(36) | Нет | `—` | Тип документа или ключ mandatory route policy | PK; FK document_types.id |
| `template_id` | VARCHAR(36) | Нет | `—` | Точная immutable версия шаблона процесса | FK workflow_templates.id |
| `reviewer_roles` | JSON | Нет | `—` | Разрешённые роли mandatory route; задаёт оператор | — |

Constraints:

- `(unnamed)` ForeignKeyConstraint (template_id)
- `(unnamed)` ForeignKeyConstraint (type_id)
- `(unnamed)` PrimaryKeyConstraint (type_id)

Indexes:

Дополнительных ORM Index нет; PK/UNIQUE создают свои индексы PostgreSQL.

## workflow_templates

| Поле | Тип | Nullable | Default | Назначение | Ограничения поля |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | Нет | `uid` (python) | Идентификатор записи; auth_sessions.id — SHA-256 session token, login_throttles.id — hash bucket | PK; — |
| `code` | VARCHAR(40) | Нет | `—` | Стабильный код справочника/маршрута | — |
| `version` | INTEGER | Нет | `—` | Номер версии шаблона по code | — |
| `name_ru` | VARCHAR(120) | Нет | `—` | Русское имя | — |
| `name_en` | VARCHAR(120) | Нет | `—` | Английское имя | — |
| `definition` | JSON | Нет | `—` | JSON stages immutable template version | — |
| `created_by` | VARCHAR(36) | Нет | `—` | Автор создания | FK users.id |
| `created_at` | DATETIME | Нет | `now()` (server) | Время создания | — |

Constraints:

- `workflow_template_positive` CheckConstraint () — `version > 0`
- `(unnamed)` ForeignKeyConstraint (created_by)
- `(unnamed)` PrimaryKeyConstraint (id)
- `uq_workflow_template_version` UniqueConstraint (code, version)

Indexes:

- `ix_workflow_templates_code` (code), unique=False
