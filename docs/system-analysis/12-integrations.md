# Integration Specification

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

| ID | Source → Destination | Protocol / Auth / Format | Request → Response | Timeout / Retry / Idempotency | Ошибка и observability |
|---|---|---|---|---|---|
| INT-01 | Browser → Next → FastAPI | Same-origin HTTP(S), cookie/CSRF/Origin; JSON или multipart | REST v1; JSON либо private stream | Fetch explicit timeout отсутствует; automatic retry нет; UUID сохраняется при network/5xx | ApiError, 401 event, X-Request-ID; backend log status/duration |
| INT-02 | API → PostgreSQL | psycopg через SQLAlchemy, DATABASE_URL secret; SQL | CRUD, row/advisory locks → result/commit | pool_pre_ping есть; explicit business statement timeout/retry не задан | ready 503 при unavailable; exceptions →500, transaction rollback при close |
| INT-03 | API → local private storage | Filesystem, process UID/volume; key-shaped paths | quarantine/save/open → bytes/immutable blob | Нет общего I/O timeout/retry; upload hash участвует в key fingerprint | Validation 422/413; missing/checksum503; audit download/upload |
| INT-04 | API → ClamAV | TCP INSTREAM, без protocol auth; private network | bounded chunks → stream: OK / FOUND | Общий deadline scan_timeout_seconds default30 (1…60); automatic retry нет | malware422, unknown/socket/timeout503; upload blocked audit |
| INT-05 | Operator → Docker / PostgreSQL / archives | CLI process credentials, dedicated backup role; dump/tar/manifest SHA | pg_dump + file archive → isolated restore verification | Поэтапный запуск; универсальный retry отсутствует; уникальные restore targets | Не перезаписывает existing DB; manifest verified_restore после проверки; tests ops |

Все подтверждённые прикладные интеграции синхронны. Асинхронный broker/outbox/worker отсутствует; operator-run cleanup не является планировщиком. due_at не инициирует уведомление или job.

При недоступности scanner upload блокируется, production download/submit требуют attestation. При PostgreSQL failure нельзя считать файл orphan и удалять его. После неизвестного commit blob сохраняется до проверенного sweep. При недоступности файла metadata может существовать, но download возвращает503.

API v1 не обещает автоматическую обратную совместимость: strict input, mandatory UUID/CAS и shape receipt требуют совместного обновления web/API. Raw OpenAPI недостаточно описывает runtime errors и security headers; клиентам нужен contract supplement. Изменение storage потребует повторного restore exercise и проверки key/path invariants. ClamAV — инфраструктурная зависимость, а не внешняя SaaS интеграция; документы не отправляются публичным сервисам.

Источник: [apps/web/src/lib/api.ts](../../apps/web/src/lib/api.ts), [apps/web/next.config.ts](../../apps/web/next.config.ts), [apps/api/app/db.py](../../apps/api/app/db.py), [apps/api/app/storage.py](../../apps/api/app/storage.py), [apps/api/app/scanning.py](../../apps/api/app/scanning.py), [ops/backup.py](../../ops/backup.py), [apps/api/app/cleanup.py](../../apps/api/app/cleanup.py).
