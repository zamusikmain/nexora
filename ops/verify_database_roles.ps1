# Dedicated PostgreSQL INSTANCE, no working service/volume changes.
$ErrorActionPreference = 'Stop'
$taskOriginalEnv = @{}
$taskEnvNames = @('POSTGRES_PASSWORD','DB_RUNTIME_PASSWORD','DB_MIGRATIONS_PASSWORD','DB_BACKUP_PASSWORD','NEXORA_ROLE_ADMIN_URL','NEXORA_TEST_ADMIN_URL','NEXORA_TEST_DATABASE_URL','NEXORA_TEST_MIGRATIONS_URL','NEXORA_TEST_BACKUP_URL','DATABASE_URL')
foreach ($taskEnvName in $taskEnvNames) { $taskOriginalEnv[$taskEnvName] = [Environment]::GetEnvironmentVariable($taskEnvName,'Process') }
try {
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskId = [Guid]::NewGuid().ToString('N').Substring(0,12)
$taskNetwork = "nexora-roles-$taskId"
$taskDb = "nexora-roles-db-$taskId"
$taskApi = "nexora-roles-api-$taskId"
# Ephemeral secrets exist only in this process and isolated containers, never in a file.
$env:POSTGRES_PASSWORD = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$env:DB_RUNTIME_PASSWORD = [Guid]::NewGuid().ToString('N')
$env:DB_MIGRATIONS_PASSWORD = [Guid]::NewGuid().ToString('N')
$env:DB_BACKUP_PASSWORD = [Guid]::NewGuid().ToString('N')
$env:NEXORA_ROLE_ADMIN_URL = "postgresql://postgres:$($env:POSTGRES_PASSWORD)@db:5432/nexora_test"
$env:NEXORA_TEST_ADMIN_URL = $env:NEXORA_ROLE_ADMIN_URL.Replace('postgresql://','postgresql+psycopg://')
$env:NEXORA_TEST_DATABASE_URL = "postgresql+psycopg://nexora_runtime:$($env:DB_RUNTIME_PASSWORD)@db:5432/nexora_test"
$env:NEXORA_TEST_MIGRATIONS_URL = "postgresql+psycopg://nexora_migrations:$($env:DB_MIGRATIONS_PASSWORD)@db:5432/nexora_test"
$env:NEXORA_TEST_BACKUP_URL = "postgresql://nexora_backup:$($env:DB_BACKUP_PASSWORD)@db:5432/nexora_test"
$env:DATABASE_URL = $env:NEXORA_TEST_DATABASE_URL
docker network create --label nexora.role-test=true $taskNetwork
if ($LASTEXITCODE -ne 0) { throw 'Network creation failed' }
docker run -d --name $taskDb --label nexora.role-test=true --network $taskNetwork --network-alias db --tmpfs /var/lib/postgresql/data:rw -e POSTGRES_PASSWORD -e POSTGRES_DB=nexora_test -e DB_BACKUP_PASSWORD -e DB_BACKUP_USER=nexora_backup postgres:17-alpine
if ($LASTEXITCODE -ne 0) { throw 'Isolated PostgreSQL startup failed' }
$taskReady = $false
for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
    docker exec $taskDb pg_isready -U postgres -d nexora_test *> $null
    if ($LASTEXITCODE -eq 0) { $taskReady=$true; break }
    Start-Sleep -Seconds 1
}
if (-not $taskReady) { throw 'Isolated PostgreSQL did not become ready' }
Write-Output "Isolated test cluster: $taskDb; network: $taskNetwork"
docker run --name $taskApi --label nexora.role-test=true --network $taskNetwork -v "${taskRoot}/apps/api:/app:ro" -v "${taskRoot}/ops:/ops:ro" -e PYTHONPATH=/ops:/app -e PYTHONDONTWRITEBYTECODE=1 -e NEXORA_ISOLATED_ROLE_TEST=isolated-docker-cluster -e NEXORA_ROLE_ADMIN_URL -e DB_RUNTIME_PASSWORD -e DB_MIGRATIONS_PASSWORD -e DB_BACKUP_PASSWORD -e NEXORA_TEST_ADMIN_URL -e NEXORA_TEST_DATABASE_URL -e NEXORA_TEST_MIGRATIONS_URL -e NEXORA_TEST_BACKUP_URL -e DATABASE_URL -e APP_ENV=development -e SEED_DEMO=false -e MALWARE_SCANNER=disabled-development nexora-api python /ops/test_database_roles.py
if ($LASTEXITCODE -ne 0) { throw "Role test suite failed; isolated resources retained: $taskDb / $taskApi" }
docker exec $taskDb sh -c 'PGPASSWORD="$DB_BACKUP_PASSWORD" pg_dump -h 127.0.0.1 --no-password -U nexora_backup -d nexora_test --no-owner --no-acl -Fc -f /tmp/roles.dump'
if ($LASTEXITCODE -ne 0) { throw 'Read-only backup role dump failed' }
docker exec $taskDb createdb -U postgres nexora_restore_test_roles
if ($LASTEXITCODE -ne 0) { throw 'Isolated restore DB creation failed' }
docker exec $taskDb psql -U postgres -d nexora_restore_test_roles -c 'ALTER SCHEMA public OWNER TO nexora_migrations;'
docker exec $taskDb pg_restore -U postgres --role=nexora_migrations -d nexora_restore_test_roles --no-owner --no-acl --exit-on-error /tmp/roles.dump
if ($LASTEXITCODE -ne 0) { throw 'Restore as migrations role failed' }
docker exec $taskDb psql -U postgres -d nexora_restore_test_roles -At -c 'SELECT (SELECT count(*) FROM documents),(SELECT count(*) FROM document_versions),(SELECT count(*) FROM audit_events),(SELECT count(*) FROM workflow_instances);'
Write-Output "Backup and restore succeeded. Resources retained for inspection: $taskDb / $taskApi"
# No container/volume removal is performed. Never use this script against a working DB.
} finally {
    foreach ($taskEnvName in $taskEnvNames) { [Environment]::SetEnvironmentVariable($taskEnvName,$taskOriginalEnv[$taskEnvName],'Process') }
}
