#Requires -Version 5.1
<#
本地开发停止脚本。
只按端口停止四端进程，不影响 docker 中间件；需要停中间件时加 -IncludeMiddleware。
#>

[CmdletBinding()]
param(
    [switch]$IncludeMiddleware
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# 端口唯一来源是根 .env：写死旧端口会误杀同机其它项目占用 8080 / 8000 / 5173 的进程
$envFile = Join-Path $repoRoot '.env'
$envMap = @{}
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $envMap[$matches[1]] = $matches[2].Trim().Trim('"')
        }
    }
}
$backendPort = if ($envMap['BACKEND_PORT']) { [int]$envMap['BACKEND_PORT'] } else { 8080 }
$agentPort = if ($envMap['AGENT_PORT']) { [int]$envMap['AGENT_PORT'] } else { 8000 }
$frontendPort = 5273
$adminPort = 5274

$targets = @(
    [pscustomobject]@{ Port = $backendPort; Name = 'application-service' },
    [pscustomobject]@{ Port = $agentPort; Name = 'agent-service' },
    [pscustomobject]@{ Port = $frontendPort; Name = 'frontend' },
    [pscustomobject]@{ Port = $adminPort; Name = 'admin' }
)

foreach ($target in $targets) {
    $owners = @(Get-NetTCPConnection -State Listen -LocalPort $target.Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)

    if ($owners.Count -eq 0) {
        Write-Host ("{0,-20} 未在运行" -f $target.Name)
        continue
    }

    foreach ($ownerId in $owners) {
        try {
            $process = Get-Process -Id $ownerId -ErrorAction Stop
            Stop-Process -Id $ownerId -Force -ErrorAction Stop
            Write-Host ("{0,-20} 已停止（PID {1}，{2}）" -f $target.Name, $ownerId, $process.ProcessName)
        } catch {
            Write-Host ("{0,-20} 停止失败：{1}" -f $target.Name, $_.Exception.Message)
        }
    }
}

if ($IncludeMiddleware) {
    Write-Host '停止中间件 postgres / pgvector / redis（保留数据卷）...' -ForegroundColor Cyan
    & docker compose -f (Join-Path $repoRoot 'docker-compose.yml') --env-file (Join-Path $repoRoot '.env') stop postgres pgvector redis
}
