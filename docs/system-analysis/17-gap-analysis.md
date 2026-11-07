# Gap Analysis

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Confirmed означает подтверждённую границу текущей реализации; это не всегда bug. Unknown/риск требует проверки. Оценки сложности S/M/L — относительные, не сроки и не коммерческие обязательства.

## GAP-001 — Обязательность маршрута не различает классификацию

- Current State: Confirmed: WorkflowRequirement PK=type_id, confidentiality отсутствует.
- Expected State (proposal): Маршрут выбирается по type+classification и не допускает downgrade.
- Business Impact: Недостаточный контроль CONFIDENTIAL/RESTRICTED.
- Technical Impact: Нужен новый policy key и safe migration.
- Priority: P0.
- Proposed Solution: Согласовать matrix, отдельно изменить schema/CLI/start tests.
- Estimated Complexity: M.
- Dependencies: Business policy, data migration rehearsal.
- Evidence: [apps/api/app/models.py](../../apps/api/app/models.py).

## GAP-002 — Неограниченная история idempotency keys

- Current State: Confirmed: operation_keys immutable, no TTL cleanup; workflow_events/audit тоже долговечны.
- Expected State (proposal): Ограничить большие responses без повторного исполнения старых ключей.
- Business Impact: Растущие storage и backup.
- Technical Impact: Просто удалить keys опасно: появятся дубликаты.
- Priority: P1.
- Proposed Solution: Tombstone actor/key/fingerprint, archived result policy, test old replay.
- Estimated Complexity: L.
- Dependencies: Retention policy, миграция trigger, client contract.
- Evidence: [apps/api/app/idempotency.py](../../apps/api/app/idempotency.py).

## GAP-003 — Raw OpenAPI не описывает session и реальные ошибки

- Current State: Confirmed: manual cookie/header; HTTPValidationError schema против envelope; dict responses.
- Expected State (proposal): Cookie/CSRF/idempotency и typed errors в generated contract.
- Business Impact: Интеграторы могут использовать неверный контракт.
- Technical Impact: Недостаточная contract validation.
- Priority: P1.
- Proposed Solution: Typed response/error schemas и explicit security/header declarations; сейчас supplement отдельно.
- Estimated Complexity: M.
- Dependencies: API compatibility decision.
- Evidence: [apps/api/app/main.py](../../apps/api/app/main.py).

## GAP-004 — Фактическое внедрение не подтверждено

- Current State: Unknown: рабочая БД не опрашивалась; base Compose использует POSTGRES_USER.
- Expected State (proposal): Изолированный restore rehearsal и проверка runtime privileges перед rollout.
- Business Impact: Нельзя обещать готовность компании.
- Technical Impact: Schema/account mismatch может остановить API.
- Priority: P0.
- Proposed Solution: Следовать role/ACL cutover, независимые offices, backup+files; отдельное разрешение внедрения.
- Estimated Complexity: M.
- Dependencies: Оператор, доступность Docker, окно изменений.
- Evidence: [compose.roles.yaml](../../compose.roles.yaml).

## GAP-005 — Дедлайны без эскалации и уведомлений

- Current State: Confirmed: due_at и overdue, нет scheduler/outbox.
- Expected State (proposal): Уведомления и выбранная escalation policy.
- Business Impact: Риск пропущенной задачи.
- Technical Impact: Нужны доставка, retry, дедупликация, ACL на payload.
- Priority: P1.
- Proposed Solution: Сначала outbox + каналы с закрытым payload; worker отдельно.
- Estimated Complexity: L.
- Dependencies: UX/business policy, infrastructure.
- Evidence: [apps/api/app/workflows.py](../../apps/api/app/workflows.py).

## GAP-006 — Локальное хранение ограничивает горизонтальный рост

- Current State: Confirmed local path; performance impact unmeasured.
- Expected State (proposal): Согласованная shared storage topology и restore.
- Business Impact: Обслуживание нескольких API узлов сложнее.
- Technical Impact: Не подтверждены RPS/latency; checksum/scanner синхронны.
- Priority: P1.
- Proposed Solution: Профилировать; проектировать private object/shared storage без public links.
- Estimated Complexity: L.
- Dependencies: Нагрузка, security, backup compatibility.
- Evidence: [apps/api/app/storage.py](../../apps/api/app/storage.py).

## GAP-007 — Недостаточная наблюдаемость зависимостей

- Current State: Confirmed logs/request_id, ready только DB; metrics/tracing нет.
- Expected State (proposal): Dependency health, scanner latency/error и DB pool alerts.
- Business Impact: Задержки и отказы трудно расследовать.
- Technical Impact: Class-only exception logs мало объясняют причину.
- Priority: P1.
- Proposed Solution: Structured safe logs/metrics; сохранять correlation, не content.
- Estimated Complexity: M.
- Dependencies: Monitoring platform, privacy rules.
- Evidence: [apps/api/app/main.py](../../apps/api/app/main.py).

## GAP-008 — Enterprise identity отсутствует

- Current State: Confirmed нет SSO/MFA/reset endpoints.
- Expected State (proposal): Выбранный IdP, revocation и MFA.
- Business Impact: Управление сотрудниками требует ручной поддержки.
- Technical Impact: Новая auth trust boundary.
- Priority: P1.
- Proposed Solution: OIDC SSO/MFA проектировать отдельно; не подменять server roles claims без mapping.
- Estimated Complexity: L.
- Dependencies: IdP, provisioning policy.
- Evidence: [apps/api/app/auth.py](../../apps/api/app/auth.py).

## GAP-009 — Отдельного независимого аудитора нет

- Current State: Confirmed enum только6 ролей; ADMIN audit ограничен query.
- Expected State (proposal): Согласовать scope расследования без blanket content.
- Business Impact: Разделение обязанностей аудита ограничено.
- Technical Impact: Нельзя просто вернуть прежний ADMIN-all.
- Priority: P2.
- Proposed Solution: Отдельные полномочия audit metadata; content только временный grant.
- Estimated Complexity: M.
- Dependencies: Business access policy.
- Evidence: [apps/api/app/catalog.py](../../apps/api/app/catalog.py).

## GAP-010 — Коллекции имеют предел без полного paging

- Current State: Confirmed users/people500, templates100, comments500, activity200, workflows20, folders200.
- Expected State (proposal): Явная pagination/truncation contract.
- Business Impact: Пользователь может не увидеть старые записи.
- Technical Impact: Нагрузочное влияние offset ACL требует измерений.
- Priority: P2.
- Proposed Solution: Cursor/page contract, UI indication, boundary tests.
- Estimated Complexity: M.
- Dependencies: Backward compatibility.
- Evidence: [apps/api/app/documents.py](../../apps/api/app/documents.py).

## GAP-011 — Непроверенная UX/accessibility матрица

- Current State: Unknown: unit RU/EN не равен полному browser/accessibility UAT.
- Expected State (proposal): Проверка keyboard/screen-reader и смешанных прав в RU/EN.
- Business Impact: Ошибки доступности могут мешать работе.
- Technical Impact: Нет доказанной browser compatibility SLA.
- Priority: P2.
- Proposed Solution: Зафиксировать browser matrix, automated UI + manual accessibility checks.
- Estimated Complexity: M.
- Dependencies: Test environment, UX reviewers.
- Evidence: [apps/web/src/lib/i18n.ts](../../apps/web/src/lib/i18n.ts).

## GAP-012 — DB и files не единая транзакция

- Current State: Confirmed blobs могут быть orphan после rollback; lost ack защищён сохранением.
- Expected State (proposal): Reconcile/backup drills регулярно и безопасно.
- Business Impact: Метаданные без file недоступны; преждевременный sweep разрушителен.
- Technical Impact: Operator cleanup есть, расписание/retention не определены.
- Priority: P1.
- Proposed Solution: Dry-run reconcile; DB-confirmed grace sweep; restore проверяет references SHA.
- Estimated Complexity: M.
- Dependencies: Backup policy, operator ownership.
- Evidence: [apps/api/app/cleanup.py](../../apps/api/app/cleanup.py).


## GAP-013 — переносимость backup unit fixture на Windows

- Current State: Confirmed в свежем запуске: test_backup_script_archives_real_private_keys подставляет str(root) в Python script без escaping; Windows `C:\Users` вызывает unicodeescape SyntaxError. Это ограничение fixture, не доказанный отказ Linux backup внутри Docker.
- Expected State (proposal): одинаковый unit test на Windows и Linux; платформенные shell prerequisites явны.
- Business Impact: нельзя получить полностью зелёную host verification только на Windows.
- Technical Impact: данный тест архивации не исполнился; другие archive integrity tests прошли.
- Priority: P2.
- Proposed Solution: fixture использует repr/posix path либо структурированный аргумент; повторить на Linux в изолированной среде. Код в этом задании не менялся.
- Estimated Complexity: S.
- Dependencies: Python/platform test environment.
- Evidence: [ops/tests/test_backup.py:17](../../ops/tests/test_backup.py#L17).
