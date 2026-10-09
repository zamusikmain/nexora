param([Parameter(Mandatory=$true)][string]$TestContainer, [int]$WebPort=13300, [int]$ApiPort=18800, [ValidateSet('127.0.0.1','localhost')][string]$HostAddress='127.0.0.1')
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskConfig=(docker inspect $TestContainer | ConvertFrom-Json)[0]
if ($taskConfig.Config.Labels.'nexora.role-test' -ne 'true') { throw 'Only a labeled isolated role-test container is allowed' }
$taskEnv=@{}
foreach ($taskEntry in $taskConfig.Config.Env) {
    $taskPair=$taskEntry.Split('=',2); $taskEnv[$taskPair[0]]=$taskPair[1]
}
if ($taskEnv['NEXORA_ISOLATED_ROLE_TEST'] -ne 'isolated-docker-cluster' -or $taskEnv['DATABASE_URL'] -notmatch '/nexora_test$') { throw 'Test guard failed' }
$taskNetwork=@($taskConfig.NetworkSettings.Networks.PSObject.Properties.Name)[0]
if ($taskNetwork -notmatch '^nexora-roles-[a-f0-9]{12}$') { throw 'Isolated network required' }
$taskSuffix=$taskNetwork.Substring('nexora-roles-'.Length)
$taskApi="nexora-acl-lab-api-$taskSuffix"
$taskWeb="nexora-acl-lab-web-$taskSuffix"
$taskSaved=@{}
$taskNames=@('DATABASE_URL','NEXORA_TEST_ADMIN_URL','WEB_ORIGIN')
try {
    foreach ($taskName in $taskNames) {
        $taskSaved[$taskName]=[Environment]::GetEnvironmentVariable($taskName,'Process')
        [Environment]::SetEnvironmentVariable($taskName,$taskEnv[$taskName],'Process')
    }
    $env:WEB_ORIGIN="http://${HostAddress}:$WebPort"
    docker run -d --name $taskApi --label nexora.acl-lab=true --network $taskNetwork --network-alias api -p "127.0.0.1:${ApiPort}:8000" --tmpfs /data/uploads:rw,uid=10001,gid=10001 -v "${taskRoot}/apps/api:/app:ro" -e DATABASE_URL -e APP_ENV=development -e WEB_ORIGIN -e SEED_DEMO=false -e MALWARE_SCANNER=disabled-development nexora-api uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Lab API startup failed' }
    for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
        try { Invoke-WebRequest "http://localhost:$ApiPort/api/v1/capabilities" -SkipHttpErrorCheck | Out-Null; break } catch { Start-Sleep -Seconds 1 }
    }
    docker run --rm --network $taskNetwork -v "${taskRoot}/apps/api:/app:ro" -v "${taskRoot}/ops:/ops:ro" -e PYTHONPATH=/ops:/app -e PYTHONDONTWRITEBYTECODE=1 -e NEXORA_ISOLATED_ROLE_TEST=isolated-docker-cluster -e NEXORA_TEST_ADMIN_URL -e DATABASE_URL -e WEB_ORIGIN nexora-api python /ops/seed_acl_lab.py
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic lab fixtures failed' }
    docker run -d --name $taskWeb --label nexora.acl-lab=true --network $taskNetwork -p "127.0.0.1:${WebPort}:3000" -e API_INTERNAL_URL=http://api:8000 nexora-acl-web
    if ($LASTEXITCODE -ne 0) { throw 'Lab web startup failed' }
    Write-Output "Isolated ACL browser lab: http://${HostAddress}:$WebPort; $taskApi / $taskWeb"
} finally {
    foreach ($taskName in $taskNames) { [Environment]::SetEnvironmentVariable($taskName,$taskSaved[$taskName],'Process') }
}
