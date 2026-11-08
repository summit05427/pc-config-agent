#Requires -Version 5.1
<#
跨服务配置一致性预检（Windows / PowerShell）。

为什么需要：JWT、模型运行时、OpenUI 是横跨根 .env、agent-service/.env、frontend/.env
的契约型配置。任何一处漏改都不会在启动时报错，只会在运行期暴露：
- JWT KID 不一致 -> Agent 验签失败 -> 前端把 401 当登录失效，把用户踢回登录页
- MODEL_RUNTIME 不一致 -> 对话绕过模型运行时，用户自填的 Key 永远不生效
- OPENUI 不一致 -> 一端产出、另一端不渲染，功能静默缺失

本脚本只读不写，存在阻断项时返回退出码 1，可被 start-local.ps1 与 CI 直接调用。
#>

[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [switch]$SkipPortCheck
)

$ErrorActionPreference = 'Stop'

$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$passes = 0

$portKeys = @(
    'WEB_PORT', 'BACKEND_PORT', 'AGENT_PORT', 'POSTGRES_PORT',
    'AGENT_POSTGRES_PORT', 'REDIS_PORT', 'LITELLM_PORT', 'PROMETHEUS_PORT'
)

function Read-DotEnv {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }

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

function Write-Pass {
    param([string]$Message)
    $script:passes += 1
    Write-Host "  [PASS] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    $script:failures.Add($Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Write-Warn {
    param([string]$Message)
    $script:warnings.Add($Message)
    Write-Host "  [WARN] $Message" -ForegroundColor Yellow
}

function Normalize-Secret {
    param([string]$Value)
    return ($Value -replace '\s', '')
}

# 比较两个文件里的同名契约键；缺失视为配置遗漏
function Assert-EnvEqual {
    param(
        [string]$Name,
        [string]$Left, [string]$LeftSource,
        [string]$Right, [string]$RightSource,
        [switch]$IgnoreWhitespace
    )

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        Write-Fail "$Name 缺失：$LeftSource 或 $RightSource 未配置"
        return
    }

    $l = if ($IgnoreWhitespace) { Normalize-Secret $Left } else { $Left }
    $r = if ($IgnoreWhitespace) { Normalize-Secret $Right } else { $Right }

    if ($l -ne $r) {
        Write-Fail "$Name 不一致：$LeftSource=$Left，$RightSource=$Right"
        return
    }

    Write-Pass "$Name 一致（$LeftSource / $RightSource）"
}

Write-Host ''
Write-Host "配置预检：$RepoRoot" -ForegroundColor Cyan

$root = Read-DotEnv -Path (Join-Path $RepoRoot '.env')
$agent = Read-DotEnv -Path (Join-Path $RepoRoot 'agent-service\.env')
$frontendPath = Join-Path $RepoRoot 'frontend\.env'
$frontend = Read-DotEnv -Path $frontendPath
$example = Read-DotEnv -Path (Join-Path $RepoRoot '.env.example')

if ($root.Count -eq 0) {
    Write-Fail "未找到根 .env，请先从 .env.example 复制并填写真实值"
}

# --- 项目身份：避免与同机已有项目共用容器、卷、网络与镜像 ---
Write-Host '项目身份' -ForegroundColor Cyan

$projectName = $root['COMPOSE_PROJECT_NAME']
if ([string]::IsNullOrWhiteSpace($projectName)) {
    Write-Fail 'COMPOSE_PROJECT_NAME 未设置，会与基线项目共用容器与数据卷'
} elseif ($projectName -notmatch '^[a-z0-9][a-z0-9_-]*$') {
    Write-Fail "COMPOSE_PROJECT_NAME 不合法：$projectName（只允许小写字母、数字、中划线、下划线）"
} else {
    Write-Pass "COMPOSE_PROJECT_NAME=$projectName"
}

$imagePrefix = $root['IMAGE_PREFIX']
if ([string]::IsNullOrWhiteSpace($imagePrefix)) {
    Write-Fail 'IMAGE_PREFIX 未设置，镜像会使用默认 agent/*，与基线项目互相覆盖'
} elseif ($imagePrefix -eq 'agent') {
    Write-Warn 'IMAGE_PREFIX=agent 与模板默认值相同，--build 会覆盖基线项目的镜像 tag'
} else {
    Write-Pass "IMAGE_PREFIX=$imagePrefix"
}

# --- 端口：八个宿主端口必须互不重复 ---
Write-Host '端口' -ForegroundColor Cyan

$missingPorts = @($portKeys | Where-Object { [string]::IsNullOrWhiteSpace($root[$_]) })
if ($missingPorts.Count -gt 0) {
    Write-Fail "端口缺失：$($missingPorts -join '、')"
} else {
    $duplicates = @($portKeys | Group-Object { $root[$_] } | Where-Object { $_.Count -gt 1 })
    if ($duplicates.Count -gt 0) {
        $detail = ($duplicates | ForEach-Object { "$($_.Name) 重复出现 $($_.Count) 次" }) -join '；'
        Write-Fail "存在重复端口：$detail"
    } else {
        $sorted = ($portKeys | ForEach-Object { $root[$_] } | Sort-Object { [int]$_ }) -join ', '
        Write-Pass "8 个宿主端口互不重复：$sorted"
    }

    if (-not $SkipPortCheck) {
        foreach ($key in $portKeys) {
            $port = [int]$root[$key]
            $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($conn) {
                $proc = (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue).ProcessName
                Write-Warn "$key=$port 已被占用（$proc / PID $($conn.OwningProcess)）；若本项目已在运行属正常"
            }
        }
    }
}

# --- 鉴权：Agent 必须用与业务端相同的 KID 和公钥验签 ---
Write-Host 'JWT 契约' -ForegroundColor Cyan

if ($agent.Count -eq 0) {
    Write-Warn '未找到 agent-service/.env，Agent 将使用默认 JWT KID，可能验签失败'
} else {
    Assert-EnvEqual -Name 'JWT KID' -Left $root['JWT_KID'] -LeftSource '根 .env JWT_KID' `
        -Right $agent['AUTH__JWT_KID'] -RightSource 'agent AUTH__JWT_KID'
    Assert-EnvEqual -Name 'JWT 公钥' -Left $root['JWT_PUBLIC_KEY'] -LeftSource '根 .env JWT_PUBLIC_KEY' `
        -Right $agent['AUTH__JWT_PUBLIC_KEY'] -RightSource 'agent AUTH__JWT_PUBLIC_KEY' -IgnoreWhitespace
}

# --- 模型运行时 / BYOK ---
Write-Host '模型运行时' -ForegroundColor Cyan

$runtimeEnabled = $root['MODEL_RUNTIME_ENABLED']
if ([string]::IsNullOrWhiteSpace($runtimeEnabled)) {
    Write-Fail '根 .env 缺少 MODEL_RUNTIME_ENABLED'
} elseif ($agent.Count -gt 0) {
    Assert-EnvEqual -Name 'MODEL_RUNTIME 开关' -Left $runtimeEnabled -LeftSource '根 MODEL_RUNTIME_ENABLED' `
        -Right $agent['MODEL_RUNTIME__ENABLED'] -RightSource 'agent MODEL_RUNTIME__ENABLED'
}

if ($root['BYOK_ENABLED'] -eq 'true') {
    if ($runtimeEnabled -ne 'true') {
        Write-Fail 'BYOK_ENABLED=true 但 MODEL_RUNTIME_ENABLED 未开启，用户自填 Key 不会生效'
    }

    $masterKey = $root['MODEL_CRED_MASTER_KEY']
    $validKey = $false
    if (-not [string]::IsNullOrWhiteSpace($masterKey)) {
        try {
            $validKey = ([Convert]::FromBase64String($masterKey)).Length -eq 32
        } catch {
            $validKey = $false
        }
    }
    if ($validKey) {
        Write-Pass 'MODEL_CRED_MASTER_KEY 为 32 字节 base64'
    } else {
        Write-Fail 'BYOK_ENABLED=true 时 MODEL_CRED_MASTER_KEY 必须是 32 字节 base64'
    }
}

$gatewayKey = $root['MODEL_GATEWAY_MASTER_KEY']
$litellmKey = $root['LITELLM_MASTER_KEY']
if ([string]::IsNullOrWhiteSpace($gatewayKey) -or [string]::IsNullOrWhiteSpace($litellmKey)) {
    Write-Warn 'MODEL_GATEWAY_MASTER_KEY 或 LITELLM_MASTER_KEY 未配置，托管模型调用会 401'
} elseif ($gatewayKey -ne $litellmKey) {
    Write-Fail 'MODEL_GATEWAY_MASTER_KEY 与 LITELLM_MASTER_KEY 不一致，业务端调用网关会 401'
} else {
    Write-Pass '网关 Master Key 与 LitellM 一致'
}

$llmKey = $root['LLM_API_KEY']
$exampleKey = $example['LLM_API_KEY']
if ([string]::IsNullOrWhiteSpace($llmKey) -or $llmKey.Length -lt 20 -or
    ($exampleKey -and $llmKey -eq $exampleKey)) {
    Write-Warn 'LLM_API_KEY 为空、过短或仍是示例值：平台托管模型会 401；仅 BYOK 场景可接受'
} else {
    Write-Pass 'LLM_API_KEY 已填写且不是示例值（建议确认是可用的真实 Key）'
}

# --- 生成式 UI：开关必须两端同步 ---
Write-Host 'OpenUI 契约' -ForegroundColor Cyan

$openuiRoot = $root['OPENUI_ENABLED']
$openuiVite = $root['VITE_OPENUI_ENABLED']
if ([string]::IsNullOrWhiteSpace($openuiRoot)) {
    Write-Warn '根 .env 未设置 OPENUI_ENABLED，默认关闭生成式 UI'
} elseif ($openuiRoot -ne $openuiVite) {
    Write-Fail "OPENUI 开关不一致：根 OPENUI_ENABLED=$openuiRoot，VITE_OPENUI_ENABLED=$openuiVite"
} elseif ($agent.Count -gt 0 -and $agent['OPENUI__ENABLED'] -ne $openuiRoot) {
    Write-Fail "OPENUI 开关不一致：根 OPENUI_ENABLED=$openuiRoot，agent OPENUI__ENABLED=$($agent['OPENUI__ENABLED'])"
} elseif ($frontend.Count -gt 0 -and $frontend['VITE_OPENUI_ENABLED'] -ne $openuiRoot) {
    Write-Fail "OPENUI 开关不一致：根 OPENUI_ENABLED=$openuiRoot，frontend/.env VITE_OPENUI_ENABLED=$($frontend['VITE_OPENUI_ENABLED'])"
} else {
    Write-Pass "OPENUI 开关两端一致：$openuiRoot"
}

if ($frontend.Count -eq 0) {
    Write-Warn '未找到 frontend/.env，本地 Vite 读不到 VITE_* 变量（标题、接口前缀、OpenUI 都会退回默认）'
} else {
    $apiBase = $frontend['VITE_API_BASE_URL']
    if ([string]::IsNullOrWhiteSpace($apiBase) -or -not $apiBase.StartsWith('/')) {
        Write-Warn "VITE_API_BASE_URL=$apiBase 不是相对路径，刷新 Cookie 可能不经 Vite 代理"
    } else {
        Write-Pass "VITE_API_BASE_URL=$apiBase"
    }
}

# --- 汇总 ---
Write-Host ''
Write-Host ("预检结果：{0} 项通过，{1} 项警告，{2} 项失败" -f $passes, $warnings.Count, $failures.Count)

if ($warnings.Count -gt 0) {
    Write-Host '警告（不阻断启动）：' -ForegroundColor Yellow
    foreach ($item in $warnings) { Write-Host "  - $item" -ForegroundColor Yellow }
}

if ($failures.Count -gt 0) {
    Write-Host '阻断项（必须先修复）：' -ForegroundColor Red
    foreach ($item in $failures) { Write-Host "  - $item" -ForegroundColor Red }
    exit 1
}

Write-Host '配置预检通过。' -ForegroundColor Green
exit 0
