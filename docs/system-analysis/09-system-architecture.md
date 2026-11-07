# System Architecture

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

## Модульный монолит

FastAPI 0.142.2 / Python 3.13 образ; SQLAlchemy, psycopg и Alembic закреплены lock-файлами. Next.js 16 / React 19 / TypeScript 5; точные resolved версии в package-lock. PostgreSQL 17-alpine; ClamAV добавляется security overlay. Это диапазоны/образы проекта, не проверка внешних latest releases.

| Модуль | Ответственность | Зависимости |
|---|---|---|
| main / body_limit | Middleware, errors, health, router composition | config / SessionLocal |
| auth | Cookie, ACTIVE, CSRF, login throttle, session lifecycle | users/auth_sessions/login_throttles |
| policy / access | SQL ACL, version grants, endorsement, receipt | auth / documents / workflow scope |
| documents / custom_fields | Карточка, file/version, comments/history, metadata | storage/scanning, models, policy |
| dms | Личное дерево, move/favorite/trash/restore/diff | documents, policy, idempotency |
| workflows | Templates, plan, stages, decisions, tasks | documents/access, idempotency |
| catalog | Users/types/departments/dashboard/audit | policy и document projection |
| ops | Backup, roles, offices, requirements | Docker/PG, отдельно от HTTP |

UI обращается к same-origin /api/v1, Next rewrites направляет на API. Cookie не содержит роль/личность. Роль загружается из users каждый запрос. API пишет результат операции и аудит в одну транзакцию PostgreSQL. Транзакция не охватывает filesystem: после upload потерянный commit acknowledgement не удаляет потенциально валидный blob; operator orphan sweep сверяет успешный полный список ссылок с БД, grace ≥24 ч (default 48), dry-run по умолчанию.

## Конкуренция и целостность

Нумерация — sequence document_number_seq, допустимы пропуски при rollback. Allocation версии — блокировка document. PATCH — expected_revision либо expected_updated_at для users/folders/types. Advisory transaction lock actor+UUID сериализует повторы; workflow actions используют workflow_events, остальные operation_keys. Личное дерево сериализуется owner lock. Immutable template versions, file versions и snapshots поддержаны триггерами миграций.

## Deployment — схема поставки, не выполненное действие

compose.yaml — development, может применять миграции при старте API, соединение через POSTGRES_USER. compose.production.yaml + compose.security.yaml — separate migrate service и production scanner, HTTPS origin обязателен. compose.roles.yaml подключается последним и меняет runtime/migrate credentials после provisioning. Сам факт наличия overlay не доказывает, что API уже не SUPERUSER. Это deployment gate, а не свойство всех запусков.

0007_acl зависит от 0006_sessions; 0008_hardening от 0007_acl. Downgrade 0007/0008 блокируется при новых бизнес-записях: безопасный откат не равен удалению новых таблиц. Для восстановления нужны согласованные DB dump + immutable files и отдельно secrets. Процедура — в существующих [cutover](../acl-cutover.md), [DB roles](../database-cutover.md), [backup](../backup-restore.md). Ни одна миграция в этом задании не запускалась.

## Диаграммы

[Component UML](diagrams/components.puml), [обзор](diagrams/architecture.mmd), [ERD](diagrams/data-model.mmd). Внешний broker и BPMN runtime не изображаются, поскольку отсутствуют.

Источники: [apps/api/requirements.lock](../../apps/api/requirements.lock), [apps/web/package-lock.json](../../apps/web/package-lock.json), [apps/api/Dockerfile](../../apps/api/Dockerfile), [apps/web/Dockerfile](../../apps/web/Dockerfile), [compose.yaml](../../compose.yaml), [compose.production.yaml](../../compose.production.yaml), [compose.roles.yaml](../../compose.roles.yaml), [apps/api/app/cleanup.py](../../apps/api/app/cleanup.py).
