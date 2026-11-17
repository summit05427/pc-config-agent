#Requires -Version 5.1
<#
Cross-service config contract check (schema driven).

Why: root .env, agent-service/.env and frontend/.env constrain each other. A missed
edit never fails at startup - it only surfaces later as a login failure, a signature
mismatch or an unreachable control plane. This script reads config/env.schema.json
and validates required keys, types, enums, port uniqueness, cross-file contracts and
derived-block freshness in one pass. It replaces the previous hand-written checks.

Usage:
  pwsh -File scripts/config/check-config.ps1                 # validate local real config
  pwsh -File scripts/config/check-config.ps1 -SkipPortCheck  # skip listening-port probe
  pwsh -File scripts/config/check-config.ps1 -ExampleOnly    # CI: only validate .env.example

ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less scripts as ANSI and
would mangle non-ASCII literals.
#>

[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$SkipPortCheck,
    [switch]$SkipDerived,
    [switch]$ExampleOnly
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot is not reliable inside param defaults on Windows PowerShell 5.1
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

$schemaPath = Join-Path $RepoRoot 'config/env.schema.json'
if (-not (Test-Path -LiteralPath $schemaPath)) {
    Write-Host "FAIL: missing config contract $schemaPath" -ForegroundColor Red
    exit 1
}
$schema = Get-Content -LiteralPath $schemaPath -Raw -Encoding UTF8 | ConvertFrom-Json

$passes = 0
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Read-DotEnv {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
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

function Test-Placeholder {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    foreach ($marker in $schema.placeholderMarkers) {
        if ($Value.ToLower().Contains($marker.ToLower())) { return $true }
    }
    return $false
}

function Expand-Template {
    param([string]$Template, [hashtable]$Values)

    return [regex]::Replace($Template, '\{([A-Za-z_][A-Za-z0-9_]*)\}', {
        param($match)
        $key = $match.Groups[1].Value
        if (-not $Values.ContainsKey($key)) {
            throw "Contract template references a key missing from root .env: $key"
        }
        return $Values[$key]
    })
}

$fileMaps = @{
    root     = Read-DotEnv -Path (Join-Path $RepoRoot $schema.files.root)
    agent    = Read-DotEnv -Path (Join-Path $RepoRoot $schema.files.agent)
    frontend = Read-DotEnv -Path (Join-Path $RepoRoot $schema.files.frontend)
    example  = Read-DotEnv -Path (Join-Path $RepoRoot $schema.files.example)
}

# --- CI mode: every key the contract needs must be declared in .env.example ---
if ($ExampleOnly) {
    $example = $fileMaps.example
    if ($example.Count -eq 0) {
        Write-Host "FAIL: missing $($schema.files.example)" -ForegroundColor Red
        exit 1
    }

    $requiredKeys = @($schema.required | ForEach-Object { $_.key })
    $typedKeys = @($schema.booleans) +
        @($schema.enums | Where-Object { $_.files -contains 'root' } | ForEach-Object { $_.key })
    $contractKeys = @($schema.contracts | ForEach-Object { $_.left })
    $needed = @($requiredKeys + $typedKeys + $contractKeys) |
        Where-Object { $_ } | Sort-Object -Unique

    $missing = @($needed | Where-Object { -not $example.ContainsKey($_) })
    if ($missing.Count -gt 0) {
        Write-Host "FAIL: .env.example is missing contract keys: $($missing -join ', ')" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK: .env.example declares $($needed.Count) contract keys" -ForegroundColor Green
    exit 0
}

# --- Local mode: validate the real configuration ---
Write-Host ''
Write-Host "Config contract check: $RepoRoot" -ForegroundColor Cyan

$root = $fileMaps.root
$agent = $fileMaps.agent
$frontend = $fileMaps.frontend

if ($root.Count -eq 0) {
    Write-Fail "Root $($schema.files.root) not found; copy .env.example and fill real values"
}

# 1. Required keys: presence, placeholder, length, pattern, PEM shape
Write-Host 'Required keys' -ForegroundColor Cyan
foreach ($rule in $schema.required) {
    $map = $fileMaps[$rule.file]
    if ($null -eq $map) { $map = @{} }
    $value = $map[$rule.key]
    $label = "$($rule.file) $($rule.key)"

    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Fail "$label is missing"
        continue
    }
    if (Test-Placeholder $value) {
        Write-Fail "$label is still a placeholder"
        continue
    }
    if ($rule.PSObject.Properties.Name -contains 'minLength' -and $value.Length -lt [int]$rule.minLength) {
        Write-Fail "$label is shorter than $($rule.minLength)"
        continue
    }
    if ($rule.PSObject.Properties.Name -contains 'pattern' -and $value -notmatch $rule.pattern) {
        $hint = if ($rule.message) { " ($($rule.message))" } else { '' }
        Write-Fail "$label does not match the required pattern: $value$hint"
        continue
    }
    if ($rule.PSObject.Properties.Name -contains 'pem') {
        $kind = $rule.pem
        if (-not ($value -match "BEGIN $kind" -and $value -match "END $kind")) {
            Write-Fail "$label is not a valid PEM (missing BEGIN/END $kind)"
            continue
        }
    }
    Write-Pass $label
}

# 2. Ports: present, valid integers, unique
Write-Host 'Ports' -ForegroundColor Cyan
$portKeys = @($schema.ports)
$missingPorts = @($portKeys | Where-Object { [string]::IsNullOrWhiteSpace($root[$_]) })
$invalidPorts = @($portKeys | Where-Object {
        $raw = $root[$_]
        if ([string]::IsNullOrWhiteSpace($raw)) { return $false }
        $number = 0
        return (-not [int]::TryParse($raw, [ref]$number)) -or $number -lt 1 -or $number -gt 65535
    })
if ($missingPorts.Count -gt 0) {
    Write-Fail "Missing ports: $($missingPorts -join ', ')"
} elseif ($invalidPorts.Count -gt 0) {
    Write-Fail "Invalid ports: $($invalidPorts -join ', ')"
} else {
    $duplicates = @($portKeys | Group-Object { $root[$_] } | Where-Object { $_.Count -gt 1 })
    if ($duplicates.Count -gt 0) {
        $detail = ($duplicates | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join '; '
        Write-Fail "Duplicate host ports: $detail"
    } else {
        $sorted = ($portKeys | ForEach-Object { $root[$_] } | Sort-Object { [int]$_ }) -join ', '
        Write-Pass "Host ports are unique: $sorted"
    }

    if (-not $SkipPortCheck) {
        foreach ($key in $portKeys) {
            $port = [int]$root[$key]
            $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($conn) {
                $proc = (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue).ProcessName
                Write-Warn "$key=$port is in use ($proc / PID $($conn.OwningProcess)); expected if this project is running"
            }
        }
    }
}

# 3. Booleans and enums: catch spelling mistakes here, not at runtime
Write-Host 'Types and enums' -ForegroundColor Cyan
foreach ($key in @($schema.booleans)) {
    if (-not $root.ContainsKey($key)) { continue }
    if ($root[$key] -notin @('true', 'false')) {
        Write-Fail "$key must be true / false, got '$($root[$key])'"
    } else {
        Write-Pass "$key=$($root[$key])"
    }
}
foreach ($enum in @($schema.enums)) {
    $key = $enum.key
    $allowed = @($enum.allowed)
    foreach ($alias in @($enum.files)) {
        $map = $fileMaps[$alias]
        if ($null -eq $map -or -not $map.ContainsKey($key)) { continue }
        if ($allowed -notcontains $map[$key]) {
            Write-Fail "$alias $key='$($map[$key])' is not one of $($allowed -join ' / ')"
        } else {
            Write-Pass "$alias $key=$($map[$key])"
        }
    }
}

# 4. Cross-file contracts: shared keys must be identical
Write-Host 'Cross-file contracts' -ForegroundColor Cyan
if ($agent.Count -eq 0) {
    Write-Warn "Missing $($schema.files.agent); skipping Agent contracts. Run scripts/config/generate-config.ps1"
} else {
    foreach ($contract in $schema.contracts) {
        $leftValue = $root[$contract.left]
        $rightValue = $agent[$contract.right]
        if ([string]::IsNullOrWhiteSpace($leftValue) -or [string]::IsNullOrWhiteSpace($rightValue)) {
            Write-Fail "$($contract.name): root $($contract.left) or agent $($contract.right) is missing"
            continue
        }
        $l = if ($contract.ignoreWhitespace) { $leftValue -replace '\s', '' } else { $leftValue }
        $r = if ($contract.ignoreWhitespace) { $rightValue -replace '\s', '' } else { $rightValue }
        if ($l -ne $r) {
            Write-Fail "$($contract.name): root $($contract.left) differs from agent $($contract.right)"
            continue
        }

        if ($contract.PSObject.Properties.Name -contains 'third') {
            $thirdMap = $fileMaps[$contract.thirdFile]
            if ($thirdMap.Count -eq 0) {
                Write-Warn "$($contract.name): $($contract.thirdFile) not found, comparison skipped"
                continue
            }
            if ($thirdMap[$contract.third] -ne $leftValue) {
                Write-Fail "$($contract.name): root $($contract.left) differs from $($contract.thirdFile) $($contract.third)"
                continue
            }
        }
        Write-Pass $contract.name
    }

    # 5. Derived URLs: structured connection strings must be recomputable from root .env
    foreach ($template in $schema.templates) {
        $expected = Expand-Template -Template $template.template -Values $root
        $actual = $fileMaps[$template.file][$template.key]
        if ($actual -ne $expected) {
            Write-Fail "$($template.name) does not match root .env; run scripts/config/generate-config.ps1"
        } else {
            Write-Pass $template.name
        }
    }
}

# 6. Combined constraints: switches and keys that only work together
Write-Host 'Combined constraints' -ForegroundColor Cyan
if ($root['BYOK_ENABLED'] -eq 'true') {
    if ($root['MODEL_RUNTIME_ENABLED'] -ne 'true') {
        Write-Fail 'BYOK_ENABLED=true but MODEL_RUNTIME_ENABLED is off; user-supplied keys will be ignored'
    } else {
        Write-Pass 'BYOK and model runtime switches match'
    }

    $masterKey = $root['MODEL_CRED_MASTER_KEY']
    $validKey = $false
    if (-not [string]::IsNullOrWhiteSpace($masterKey)) {
        try { $validKey = ([Convert]::FromBase64String($masterKey)).Length -eq 32 } catch { $validKey = $false }
    }
    if ($validKey) {
        Write-Pass 'MODEL_CRED_MASTER_KEY is 32 bytes of base64'
    } else {
        Write-Fail 'BYOK_ENABLED=true requires MODEL_CRED_MASTER_KEY to be 32 bytes of base64'
    }
}

$gatewayKey = $root['MODEL_GATEWAY_MASTER_KEY']
$litellmKey = $root['LITELLM_MASTER_KEY']
if ([string]::IsNullOrWhiteSpace($gatewayKey) -or [string]::IsNullOrWhiteSpace($litellmKey)) {
    Write-Warn 'MODEL_GATEWAY_MASTER_KEY or LITELLM_MASTER_KEY is empty; managed models will get 401'
} elseif ($gatewayKey -ne $litellmKey) {
    Write-Fail 'MODEL_GATEWAY_MASTER_KEY differs from LITELLM_MASTER_KEY; gateway calls will get 401'
} else {
    Write-Pass 'Gateway master key matches LiteLLM'
}

$llmKey = $root['LLM_API_KEY']
if ([string]::IsNullOrWhiteSpace($llmKey) -or $llmKey.Length -lt 20 -or (Test-Placeholder $llmKey)) {
    Write-Warn 'LLM_API_KEY is empty, too short or still a placeholder; managed models will get 401 (BYOK-only is fine)'
} else {
    Write-Pass 'LLM_API_KEY is set'
}

# 7. Derived block freshness: service-level .env must match root .env
if (-not $SkipDerived) {
    Write-Host 'Derived config' -ForegroundColor Cyan
    $generator = Join-Path $RepoRoot 'scripts/config/generate-config.ps1'
    & $generator -RepoRoot $RepoRoot -Check
    if ($LASTEXITCODE -ne 0) {
        Write-Fail 'Service .env managed block is stale; run scripts/config/generate-config.ps1'
    }
}

# --- Summary ---
Write-Host ''
Write-Host ("Result: {0} passed, {1} warning(s), {2} failure(s)" -f $passes, $warnings.Count, $failures.Count)

if ($warnings.Count -gt 0) {
    Write-Host 'Warnings (non-blocking):' -ForegroundColor Yellow
    foreach ($item in $warnings) { Write-Host "  - $item" -ForegroundColor Yellow }
}
if ($failures.Count -gt 0) {
    Write-Host 'Blocking issues (fix before starting):' -ForegroundColor Red
    foreach ($item in $failures) { Write-Host "  - $item" -ForegroundColor Red }
    exit 1
}

Write-Host 'Config contract check passed.' -ForegroundColor Green
exit 0
