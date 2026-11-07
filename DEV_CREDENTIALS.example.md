# Development Credentials — публичный шаблон NEXORA

Скопируйте этот файл в `DEV_CREDENTIALS.local.md`. Заполняйте только данными из своего локального тестового окружения. Локальная копия исключена из Git и Docker build contexts. Не помещайте её в `apps/web/src`, `public`, переменные `NEXT_PUBLIC_*`, CI artifacts или логи. Поля ниже намеренно пустые.

## Local Environment

Application URL:

API URL:

Environment: development

Last verification:

## Test Accounts

Повторяйте блок для **каждого пользователя каждого окружения**, даже если роли совпадают. Одинаковый email в двух БД — две отдельные записи. Не объединяйте пользователей по роли.

### Полная запись пользователя — копируемый блок

Environment / Database:
Source / provenance:
User ID:
Login:
Password:
Role:
Account status:
Login URL:
Authentication type: Local
Purpose:
Verification: NOT VERIFIED
Verification date:
Password reset scope:
Limitations:

Password заполняется только конкретным известным или безопасно установленным тестовым паролем. Не используйте вымышленные значения. Для OAuth оставьте поле пустым и укажите провайдера. Успешный вход на копии доказывает вход только на этой копии; не помечайте исходное окружение VERIFIED по такой проверке.

### USER — инициатор

Login:
Password:
Role: USER
Status: NOT VERIFIED

### REVIEWER — проверяющий

Login:
Password:
Role: REVIEWER
Status: NOT VERIFIED

### APPROVER — согласующий

Login:
Password:
Role: APPROVER
Status: NOT VERIFIED

### LEGAL — юридическая проверка

Login:
Password:
Role: LEGAL
Status: NOT VERIFIED

### MANAGER — руководитель отдела

Login:
Password:
Role: MANAGER
Status: NOT VERIFIED

### ADMIN — технический администратор

Login:
Password:
Role: ADMIN
Status: NOT VERIFIED

### USER — дополнительный пользователь другого отдела

Login:
Password:
Role: USER
Status: NOT VERIFIED

## Authentication

Authentication type: Local.

Локальный email/password, Argon2id, серверная HttpOnly cookie, ACTIVE status, CSRF token и проверка Origin на изменяющих запросах. OAuth/OIDC/SSO в текущем коде не реализованы. Саморегистрации и API создания пользователей нет. Роль ADMIN не даёт автоматического доступа к чужому содержимому.

## Notes — безопасное создание и проверка

1. Источник demo-набора: `apps/api/app/seed.py`. Он определяет семь синтетических учётных записей с шестью ролями, но определение в seed не доказывает наличие аккаунта в БД.
2. Только для отдельной локальной development-БД оператор задаёт `APP_ENV=development`, `SEED_DEMO=true` и уникальный тестовый `DEMO_PASSWORD` длиной не менее 12 символов. Не используйте production secrets. Не запускайте seed на рабочей базе только ради этой инструкции: он создаёт в том числе ADMIN.
3. После отдельного разрешения на создание demo-набора оператор выполняет `python -m app.seed` в API-окружении, явно подключённом к этой тестовой БД. БД должна уже иметь совместимую схему. В этом задании команды seed и миграций не выполняются.
4. Seed добавляет только отсутствующих пользователей; существующие пароли и роли не сбрасываются. Поэтому текущий `DEMO_PASSWORD` может не подходить ранее созданным аккаунтам. Не восстанавливайте пароль из hash и не меняйте его без разрешения.
5. Для проверки войдите через локальную страницу `/login` и сверяйте роль из ответа сервера. VERIFIED ставится только после успешного входа. NOT VERIFIED означает, что существование, текущие права или пароль ещё не подтверждены.
6. Вход пишет аудит, throttle и session records. Проверяйте только явно локальные тестовые аккаунты, не внешние сервисы. При неизвестном пароле оставьте поле пустым и запросите известный тестовый пароль у разработчика.

CUSTODIAN и SECURITY — временные department-scoped полномочия, а не отдельные роли входа. Их назначение требует независимых лиц и разрешения оператора. `ops/seed_acl_lab.py` и pytest создают отдельные временные fixtures в изолированной `nexora_test`; не переносите их в основную demo-БД. Для лабораторий используйте отдельный блок и укажите точное окружение, не объявляя fixtures рабочими аккаунтами.

Локальный файл хранит plaintext, если пароль заполнен. `.gitignore` не заменяет шифрование: не синхронизируйте и не публикуйте файл, не выводите его в терминал/CI. Для общих рабочих станций предпочтительнее локальный менеджер паролей.
