# Security & Access — ACL Revision 2 AS-IS

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

## Authentication и граница доверия

Argon2id, token_urlsafe cookie, SHA-256 session token в БД, CSRF compare_digest и exact Origin на mutations. Сессия default12h, максимум20 активных; login throttle 20 failures/15 минут по account и direct peer. Forwarded client IP не принимается доверенно. ACTIVE проверяется каждым запросом. MFA, SSO, password reset и self-signup не подтверждены в коде.

## Матрица

| Role / Context | Resource | Action | Allowed | Conditions |
|---|---|---|---|---|
| Все 6 ACTIVE user.roles | Новый документ | create | Да | Сервер owner/dept; type/metadata valid |
| Owner любой роли | Свой документ/версия | card/file/history/compare | Да | Независимый owner scope; старые версии также; scan/integrity для файла |
| Owner | Карточка/версия | edit/upload | Условно | DRAFT/REVISION_REQUIRED, не trash, CAS где требуется |
| Owner | Процесс | start/cancel | Условно | Допустимое состояние, файл/scan/route; owner не self-reviewer |
| MANAGER | Документ отдела | card/file | Условно | APPROVED PUBLIC/INTERNAL, current version, не trash |
| MANAGER | Черновик отдела | card/file | По персональному draft grant | Enabled policy, явная передача owner, PUBLIC/INTERNAL; captured current MANAGER audience |
| MANAGER | CONFIDENTIAL / RESTRICTED | card/file | Нет по роли | Нужны owner / active assignment / проверенный grant |
| ADMIN | Чужое содержимое | card/file/history | Нет по роли | Обычные owner/assignment/grant основания независимо от ADMIN |
| REVIEWER/APPROVER/LEGAL/USER/ADMIN/MANAGER | Активное назначение | card/file/decision | Условно | Свой PENDING, current stage, RUNNING, IN_APPROVAL, pinned version; RESTRICTED card+file grants |
| Future participant | Будущий этап | card/file | Нет по назначению | WAITING не даёт scope; независимый owner/grant может иметь своё основание |
| Finished/cancelled participant | Прежний документ/новая версия | card/file | Нет по назначению | Собственная receipt не является content grant |
| Автор решения | Своя receipt | read | Да условно | Не hide_receipt; can_download=false; cancelled summary без content |
| Автор решения | Frozen own snapshot | read | Условно | Nonrestricted RUNNING <7 дней; либо действующий snapshot grant; не trash/revoked |
| Любой участник | Чужая receipt | read | Нет | 404 |
| Active participant | Comments | read/write | Условно | Сервер ограничивает текущими stage/instance/version; вне review нужен explicit comments scope |
| Non-owner card reader | History / compare | read | Нет по card | Отдельный history/compare grant; diff проверяет обе версии |
| ADMIN | Users/types/templates/sessions | admin | Да | Server permission; CAS, запрет менять себя; без password_hash |
| ADMIN | Global audit | read | Ограничено | document target только своих документов; other targets по server query |
| CUSTODIAN / SECURITY office | Документ | content | Нет по office | Office даёт управление grants, не автоматическое чтение |
| CUSTODIAN | Department policy / requests | manage | Условно | Department-scoped active unexpired office |
| CUSTODIAN + SECURITY | RESTRICTED grant | endorse | Условно | Два разных actor; не requester/recipient; один vote/office; scope_hash совпадает |
| Requester/recipient/owner/offices | Доступный grant | revoke | Да | Проверка visible_grant; повтор terminal no-op |
| BLOCKED / DISABLED | Любой protected resource | any | Нет | 401 ещё на current_user |

## Допуск и версия

Personal grants: actions card/file/snapshot/comments/history/compare, duration1…168h; RESTRICTED максимум8h, два votes за24h. Scope содержит doc/version, classification, department, recipient role/dept, requester, purpose и hash. На каждом чтении проверяются текущая роль/отдел/ACTIVE, срок и revoke, offices и необходимость review. Нельзя переносить endorsements на новый scope; нельзя возобновить terminal grant. Для ordinary snapshot explicit grant также должен соответствовать собственному approval; snapshot не содержит файла.

Версии в list отфильтрованы file scope. Поиск использует frozen title/status для review/grant, dashboard ту же visibility. UI capabilities не являются защитой: сервер проверяет запрос независимо от кнопки. GET grants может обновлять expired status; чтение API не всегда read-only для БД. Download пишет аудит.

Секреты — env вне Git; storage_key никогда публичный URL. API errors скрывают наличие недоступного ресурса404; Forbidden используется для явного permission violation. Потребность независимого enterprise аудитора — gap, отдельной роли AUDITOR нет. Политика PostgreSQL runtime/migrations/backup требует явного provisioning/overlay; наличие кода не подтверждает права deployed account.

Источник: [apps/api/app/auth.py](../../apps/api/app/auth.py), [apps/api/app/policy.py](../../apps/api/app/policy.py), [apps/api/app/access.py](../../apps/api/app/access.py), [apps/api/app/documents.py](../../apps/api/app/documents.py), [apps/api/app/catalog.py](../../apps/api/app/catalog.py), [ops/database_roles.py](../../ops/database_roles.py).
