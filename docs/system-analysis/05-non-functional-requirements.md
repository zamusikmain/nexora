# Non-Functional Requirements

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Ни uptime, ни RPS, ни latency ниже не заявлены измеренными. Все TO-BE — предложения; факт отдельного unit теста не подтверждает SLA.

## NFR-001 — Performance

AS-IS: Синхронный scanner, полное SHA файла перед download, offset pagination; нагрузочные показатели Unknown.

TO-BE / Proposed acceptance: Измерить p95/p99 list/upload/download и блокировки на согласованном наборе данных; численные цели сначала согласовать.

Источник: [apps/api/app/documents.py](../../apps/api/app/documents.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-002 — Availability

AS-IS: health без зависимостей; ready проверяет PostgreSQL, не storage/ClamAV; SLA Unknown.

TO-BE / Proposed acceptance: Определить SLO после анализа потребностей; отдельные dependency probes и упражнения отказа.

Источник: [apps/api/app/main.py](../../apps/api/app/main.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-003 — Reliability

AS-IS: Ключ actor+UUID, транзакционные результаты, safe retry; lifecycle keys отсутствует.

TO-BE / Proposed acceptance: Tombstone после удаления response; никогда не исполнять старый ключ снова.

Источник: [apps/api/app/idempotency.py](../../apps/api/app/idempotency.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-004 — Security

AS-IS: ACTIVE + cookie + CSRF + origin; version/action ACL; scanner fail-closed production.

TO-BE / Proposed acceptance: MFA/SSO и регулярная проверка BOLA, независимость полномочий.

Источник: [apps/api/app/auth.py](../../apps/api/app/auth.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-005 — Scalability

AS-IS: SQL pool_pre_ping; локальные volumes; нет распределённой файловой топологии.

TO-BE / Proposed acceptance: Профилирование запросов ACL; сначала измерить, затем indexes/cursor/shared storage.

Источник: [apps/api/app/db.py](../../apps/api/app/db.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-006 — Maintainability

AS-IS: Модули FastAPI, typed schemas, pytest, Ruff/mypy, TS; framework version locks.

TO-BE / Proposed acceptance: Контрактные тесты схем и проверка аналитических links в CI.

Источник: [apps/api/app/schemas.py](../../apps/api/app/schemas.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-007 — Observability

AS-IS: X-Request-ID, method/status/duration, transactional audit; нет metrics/tracing.

TO-BE / Proposed acceptance: Метрики сканера/БД/конфликтов и alerting без document payload.

Источник: [apps/api/app/main.py](../../apps/api/app/main.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-008 — Data Integrity

AS-IS: Sequence, row locks, composite FK, immutable triggers, checksum; DB+FS не одна транзакция.

TO-BE / Proposed acceptance: Периодический dry-run reconcile и проверенное восстановление DB+files.

Источник: [apps/api/app/documents.py](../../apps/api/app/documents.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-009 — Usability

AS-IS: RU/EN, localStorage language, task kinds, capability-aware UI; accessibility UAT Unknown.

TO-BE / Proposed acceptance: Проверка keyboard/screen reader, обеих локалей и сетевых ошибок с пользователями.

Источник: [apps/api/app/workflows.py](../../apps/api/app/workflows.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.

## NFR-010 — Compatibility

AS-IS: API v1, strict input extra=forbid, additive migrations до 0008, guarded downgrade.

TO-BE / Proposed acceptance: Версионирование контрактов и upgrade rehearsal на копии; browser support matrix согласовать.

Источник: [apps/api/app/models.py](../../apps/api/app/models.py). Статус: Partially implemented относительно предложения; подтверждённые механизмы перечислены выше, целевые показатели Unknown.
