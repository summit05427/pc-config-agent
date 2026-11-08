#Requires -Version 5.1
<#
本地开发一键启动脚本（Windows / PowerShell）。
设计意图：
1. 口令、JWT 密钥统一从仓库根 .env 读取，避免手工设置 DB_PASSWORD 时误用示例值或旧值。
2. 启动 Java 前先用真实网络路径校验数据库口令，避免 Flyway 报错掩盖根因。
3. 四端各自在独立后台进程运行，日志写到 logs/dev，便于排查。
#>

[CmdletBinding()]
param(
    [ValidateSet('all', 'application', 'agent', 'frontend', 'admin')]
    [string]$Service = 'all',

    [switch]$SkipMiddleware
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envFile = Join-Path $repoRoot '.env'
$composeFile = Join-Path $repoRoot 'docker-compose.yml'
$logDir = Join-Path $repoRoot 'logs\dev'

# 前端开发端口与同机其它项目错开；Java / Agent 端口以根 .env 为准（见下方读取）
$frontendPort = 5273
$adminPort = 5274

function Read-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "未找到 $Path。请先从根 .env.example 复制为 .env 并填写真实值。"
    }

    $map = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $value = $matches[2].Trim()
            if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $map[$matches[1]] = $value
        }
    }
    return $map
}

function Assert-RequiredKeys {
    param([hashtable]$Map, [string[]]$Keys)

    $missing = @($Keys | Where-Object { [string]::IsNullOrWhiteSpace($Map[$_]) })
    if ($missing.Count -gt 0) {
        throw "根 .env 缺少必填变量：$($missing -join '、')"
    }
}

function Test-PortInUse {
    param([int]$Port)

    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Resolve-Executable {
    param([string]$Name, [string[]]$Fallbacks = @())

    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    foreach ($fallback in $Fallbacks) {
        if (Test-Path -LiteralPath $fallback) { return $fallback }
    }
    throw "未找到 $Name，请安装后加入 PATH。"
}

function Set-JavaEnvironment {
    param([hashtable]$Map)

    $values = [ordered]@{
        SPRING_PROFILES_ACTIVE = 'local'
        DB_USERNAME = $Map['POSTGRES_USER']
        DB_PASSWORD = $Map['POSTGRES_PASSWORD']
        JWT_PRIVATE_KEY = $Map['JWT_PRIVATE_KEY']
        JWT_PUBLIC_KEY = $Map['JWT_PUBLIC_KEY']
        JWT_KID = $Map['JWT_KID']
        JWT_ISSUER = $Map['JWT_ISSUER']
        JWT_AUDIENCE = $Map['JWT_AUDIENCE']
        AUTH_ADMIN_USERNAME = $Map['AUTH_ADMIN_USERNAME']
        AUTH_ADMIN_PASSWORD = $Map['AUTH_ADMIN_PASSWORD']
        AUTH_ADMIN_ROLES = $Map['AUTH_ADMIN_ROLES']
        AUTH_DEMO_USERNAME = $Map['AUTH_DEMO_USERNAME']
        AUTH_DEMO_PASSWORD = $Map['AUTH_DEMO_PASSWORD']
        AUTH_DEMO_ROLES = $Map['AUTH_DEMO_ROLES']
        AUTH_COOKIE_SECURE = 'false'
        CORS_ALLOWED_ORIGINS = "http://localhost:$frontendPort,http://localhost:$adminPort,http://127.0.0.1:$frontendPort,http://127.0.0.1:$adminPort"
        MODEL_RUNTIME_ENABLED = $Map['MODEL_RUNTIME_ENABLED']
        MODEL_DEFAULT_KEY = $Map['MODEL_DEFAULT_KEY']
        BYOK_ENABLED = $Map['BYOK_ENABLED']
        MODEL_CRED_MASTER_KEY = $Map['MODEL_CRED_MASTER_KEY']
        MODEL_CRED_KEY_VERSION = '1'
        INTERNAL_AUTH_CLIENT_ID = 'agent-service'
        INTERNAL_AUTH_CLIENT_SECRET = $Map['INTERNAL_AUTH_CLIENT_SECRET']
    }

    foreach ($key in $values.Keys) {
        if ($null -ne $values[$key] -and "$($values[$key])".Trim() -ne '') {
            Set-Item -Path "Env:$key" -Value $values[$key]
        }
    }
}

function Test-DatabasePassword {
    param([hashtable]$Map)

    # 必须从容器网络连接（scram-sha-256）；容器内 127.0.0.1 走 trust，测不出真实口令
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & docker compose -f $composeFile --env-file $envFile exec -T `
            -e "PGPASSWORD=$($Map['POSTGRES_PASSWORD'])" pgvector `
            psql -h postgres -U $Map['POSTGRES_USER'] -d $Map['POSTGRES_DB'] -tAc 'select 1' 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return ($exitCode -eq 0 -and $output.Trim() -eq '1')
}

function Start-DevProcess {
    param([string]$Name, [string]$Command, [string]$WorkingDirectory)

    $stdout = Join-Path $logDir "$Name.log"
    $stderr = Join-Path $logDir "$Name.err.log"
    $runner = Join-Path $logDir "$Name.run.cmd"
    $launcher = Join-Path $logDir "$Name.cmd"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    # 实际命令写进 runner：Start-Process 直接传带引号的长命令会被 cmd 拆错
    $runnerContent = @(
        '@echo off',
        "cd /d `"$WorkingDirectory`"",
        "$Command > `"$stdout`" 2> `"$stderr`""
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($runner, $runnerContent, $utf8NoBom)

    # launcher 用 start 开独立控制台：关闭启动终端不会连带杀掉四端进程
    $launcherContent = @(
        '@echo off',
        "start `"$Name`" /min cmd /c `"$runner`""
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($launcher, $launcherContent, $utf8NoBom)

    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', "`"$launcher`"" -WindowStyle Hidden | Out-Null
}

function Wait-Endpoint {
    param([string]$Url, [int]$TimeoutSeconds = 120)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Write-Summary {
    param([System.Collections.Specialized.OrderedDictionary]$Rows)

    Write-Host ''
    Write-Host '服务状态' -ForegroundColor Cyan
    foreach ($name in $Rows.Keys) {
        $row = $Rows[$name]
        Write-Host ("  {0,-20} {1,-32} {2}" -f $name, $row.Url, $row.Status)
    }
    Write-Host ''
    Write-Host "日志目录：$logDir"
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$dotenv = Read-DotEnv -Path $envFile
Assert-RequiredKeys -Map $dotenv -Keys @(
    'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
    'JWT_PRIVATE_KEY', 'JWT_PUBLIC_KEY', 'AUTH_ADMIN_PASSWORD'
)

# 端口唯一来源是根 .env（与 docker-compose.yml 的宿主映射保持一致），避免脚本与编排漂移
$backendPort = if ($dotenv['BACKEND_PORT']) { [int]$dotenv['BACKEND_PORT'] } else { 18080 }
$agentPort = if ($dotenv['AGENT_PORT']) { [int]$dotenv['AGENT_PORT'] } else { 18000 }

if (-not $SkipMiddleware) {
    Write-Host '启动中间件 postgres / pgvector / redis ...' -ForegroundColor Cyan
    & docker compose -f $composeFile --env-file $envFile up -d postgres pgvector redis
}

# 管理端按独立策略启动：默认 all 只拉起三个业务端，admin 需显式指定
$targets = if ($Service -eq 'all') { @('application', 'agent', 'frontend') } else { @($Service) }
$rows = [ordered]@{}

if ($targets -contains 'application') {
    if (-not (Test-DatabasePassword -Map $dotenv)) {
        throw @'
数据库口令校验失败：根 .env 的 POSTGRES_PASSWORD 与数据库实际口令不一致。
注意：POSTGRES_PASSWORD 只在数据卷首次初始化时生效，修改 .env 不会改已有角色口令。
请核对数据库真实口令，或先执行 ALTER ROLE 再同步 .env；确认中间件已启动。
'@
    }

    if (Test-PortInUse -Port $backendPort) {
        $rows['application-service'] = @{ Url = "http://localhost:$backendPort"; Status = '已在运行，跳过' }
    } else {
        Set-JavaEnvironment -Map $dotenv
        Start-DevProcess -Name 'application-service' `
            -Command '.\mvnw.cmd spring-boot:run' `
            -WorkingDirectory (Join-Path $repoRoot 'application-service')
        Write-Host 'application-service 启动中...' -ForegroundColor Cyan
        $rows['application-service'] = @{ Url = "http://localhost:$backendPort"; Status = '启动中' }
    }
}

if ($targets -contains 'agent') {
    if (Test-PortInUse -Port $agentPort) {
        $rows['agent-service'] = @{ Url = "http://localhost:$agentPort"; Status = '已在运行，跳过' }
    } else {
        $uv = Resolve-Executable -Name 'uv' -Fallbacks @(
            (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
            (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe')
        )
        Start-DevProcess -Name 'agent-service' `
            -Command "`"$uv`" run python run.py" `
            -WorkingDirectory (Join-Path $repoRoot 'agent-service')
        Write-Host 'agent-service 启动中...' -ForegroundColor Cyan
        $rows['agent-service'] = @{ Url = "http://localhost:$agentPort"; Status = '启动中' }
    }
}

if ($targets -contains 'frontend' -or $targets -contains 'admin') {
    $nodePath = Resolve-Executable -Name 'node'
    $corepack = Join-Path (Split-Path -Parent $nodePath) 'corepack.cmd'
}

if ($targets -contains 'frontend') {
    if (Test-PortInUse -Port $frontendPort) {
        $rows['frontend'] = @{ Url = "http://localhost:$frontendPort"; Status = '已在运行，跳过' }
    } else {
        Start-DevProcess -Name 'frontend' -Command "`"$corepack`" pnpm dev" `
            -WorkingDirectory (Join-Path $repoRoot 'frontend')
        Write-Host 'frontend 启动中...' -ForegroundColor Cyan
        $rows['frontend'] = @{ Url = "http://localhost:$frontendPort"; Status = '启动中' }
    }
}

if ($targets -contains 'admin') {
    if (Test-PortInUse -Port $adminPort) {
        $rows['admin'] = @{ Url = "http://localhost:$adminPort"; Status = '已在运行，跳过' }
    } else {
        Start-DevProcess -Name 'admin' -Command "`"$corepack`" pnpm dev" `
            -WorkingDirectory (Join-Path $repoRoot 'admin')
        Write-Host 'admin 启动中...' -ForegroundColor Cyan
        $rows['admin'] = @{ Url = "http://localhost:$adminPort"; Status = '启动中' }
    }
}

if ($targets -contains 'application' -and $rows.Contains('application-service') -and $rows['application-service'].Status -eq '启动中') {
    $ok = Wait-Endpoint -Url "http://127.0.0.1:$backendPort/actuator/health" -TimeoutSeconds 180
    $rows['application-service'].Status = if ($ok) { 'UP' } else { "未就绪，见 $logDir\application-service.log" }
}
if ($targets -contains 'agent' -and $rows.Contains('agent-service') -and $rows['agent-service'].Status -eq '启动中') {
    $ok = Wait-Endpoint -Url "http://127.0.0.1:$agentPort/api/v1/health/live" -TimeoutSeconds 90
    $rows['agent-service'].Status = if ($ok) { 'UP' } else { "未就绪，见 $logDir\agent-service.log" }
}
if ($targets -contains 'frontend' -and $rows.Contains('frontend') -and $rows['frontend'].Status -eq '启动中') {
    $ok = Wait-Endpoint -Url "http://localhost:$frontendPort" -TimeoutSeconds 60
    $rows['frontend'].Status = if ($ok) { 'UP' } else { "未就绪，见 $logDir\frontend.log" }
}
if ($targets -contains 'admin' -and $rows.Contains('admin') -and $rows['admin'].Status -eq '启动中') {
    $ok = Wait-Endpoint -Url "http://localhost:$adminPort" -TimeoutSeconds 60
    $rows['admin'].Status = if ($ok) { 'UP' } else { "未就绪，见 $logDir\admin.log" }
}

Write-Summary -Rows $rows

if (($rows.Values | Where-Object { $_.Status -notmatch '^(UP|已在运行)' }).Count -gt 0) {
    exit 1
}
