# Stage 8 release verification entry point.
#
# Why: the hardware source data lives on a local disk and is too large for cloud CI,
# so full-data regeneration is verified by this script instead. Each step must pass;
# any non-zero exit stops the run immediately.
#
# Usage:
#   powershell -File scripts/pc-config/verify-release.ps1 -DataDir "F:\LLM_PC_Agent\Hardware data"
#
# ASCII-only comments: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.

param(
    [Parameter(Mandatory = $true)][string]$DataDir
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $DataDir)) {
    Write-Host "FAIL: data directory not found: $DataDir"
    exit 1
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location -LiteralPath $repoRoot

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "==> $Name"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $Name (exit code $LASTEXITCODE)"
        Pop-Location
        exit 1
    }
}

try {
    Invoke-Step 'unit tests' {
        python -m pytest scripts/pc-config/tests -q
    }

    Invoke-Step 'baseline inspection' {
        python scripts/pc-config/inspect_dataset.py --data-dir $DataDir
    }

    Invoke-Step 'schema export' {
        python scripts/pc-config/hardware_schema.py --export-dir data/pc-config/schema
    }

    Invoke-Step 'dataset validation' {
        python scripts/pc-config/validate_dataset.py --root data/pc-config
    }

    Invoke-Step 'release dry run' {
        python scripts/pc-config/publish_candidates.py --dry-run
    }

    Write-Host 'OK: Stage 8 release verification passed'
} finally {
    Pop-Location
}
