# Verify that every environment variable mentioned in Markdown exists in some .env.example.
#
# Why: docs drift faster than code. A renamed variable (e.g. AUTH__JWT_ISSUER ->
# AUTH__ISSUER) leaves stale names in guides, and readers copy them into .env,
# where pydantic-settings silently ignores unknown keys.
#
# Scope: all Markdown files under docs/, the three service READMEs and the root README.
# A key counts as documented if it appears anywhere in a *.env.example file,
# including commented-out lines (optional variables are often commented out).
#
# Written for PowerShell 5.1: ASCII-only comments, explicit UTF-8 reads.

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$envExampleName = '*.env.example'

# Only match names that really look like environment variables. Free-form uppercase
# words in prose (HTTP, SSE, ADMIN, ISO-8601) must not be treated as config keys.
$keyPattern = @(
    '\b[A-Z][A-Z0-9]*__[A-Z][A-Z0-9_]*\b'
    '\bVITE_[A-Z0-9_]+\b'
    '\bLANGSMITH_[A-Z0-9_]+\b'
    '\bJWT_[A-Z0-9_]+\b'
    '\bPOSTGRES_[A-Z0-9_]+\b'
    '\bAGENT_POSTGRES_[A-Z0-9_]+\b'
    '\bCOMPOSE_[A-Z0-9_]+\b'
    '\bREDIS_PASSWORD\b'
    '\bAPP_NAME\b'
    '\bAPP_ENV\b'
    '\bAPI_PREFIX\b'
    '\bCORS_ORIGINS\b'
    '\bCORS_ALLOWED_ORIGINS\b'
    '\bAUTH_USERNAME\b'
    '\bAUTH_PASSWORD\b'
    '\bAUTH_ROLES\b'
    '\bLLM_API_KEY\b'
    '\bLLM_MODEL\b'
    '\bLLM_BASE_URL\b'
) -join '|'

# Keys that are intentionally mentioned but never configured through .env.
# Keep this list explicit and commented; an empty list is the healthy state.
# 2026-11-10 cleanup: JWT_SECRET / AUTH_USERNAME / AUTH_PASSWORD / AUTH_ROLES are no
# longer quoted anywhere; MODEL_RUNTIME__* is now declared in agent-service/.env.example.
# Keeping dead entries here would hide the next rename.
$allowedMissing = @(
    # Historical names removed on 2026-10-28; docs quote them only to explain the fix.
    'AUTH__JWT_ISSUER'
    'AUTH__JWT_ALGORITHM'
    'AUTH__JWT_SECRET'
    # Solver path removed on 2026-11-17 (commit dda3829). ADR 0028 and the PC handoff
    # docs quote these names only to record the superseded transition-period design.
    'AGENT__MAX_SOLVE_RETRIES'
    'AGENT__PC_SELECTION_MODE'
    # Rotation placeholder: the code only verifies one public key by kid and never reads
    # this key; environment-variables.md mentions it to explain the single-kid limitation.
    'JWT_PREVIOUS_PUBLIC_KEY'
    # HS256-era name; architecture.md A-01 uses it to explain the rename history.
    'AUTH__ALGORITHM'
    # Negative examples: forbidden KEY names that the frontend build check rejects.
    'VITE_API_KEY'
    'VITE_JWT_SECRET'
)

function Read-TextFileUtf8([System.IO.FileInfo]$File) {
    return [System.IO.File]::ReadAllText($File.FullName, [System.Text.Encoding]::UTF8)
}

# 1. Collect every key declared in any .env.example (commented lines included).
# Why manual walk: Get-ChildItem -Recurse descends into node_modules before the
# path filter runs, and a single broken junction there aborts the whole gate.
function Get-EnvExampleFiles([string]$Root) {
    $ignored = @('node_modules', '.git', '.venv', 'target', 'dist')
    $files = New-Object 'System.Collections.Generic.List[System.IO.FileInfo]'
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        try {
            $entries = Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop
        } catch {
            continue
        }
        foreach ($entry in $entries) {
            if ($entry.PSIsContainer) {
                if ($ignored -contains $entry.Name) { continue }
                $pending.Push($entry.FullName)
            } elseif ($entry.Name -like $envExampleName) {
                $files.Add($entry)
            }
        }
    }
    return $files
}

$declared = New-Object 'System.Collections.Generic.HashSet[string]'
$envFiles = Get-EnvExampleFiles -Root $repoRoot

foreach ($envFile in $envFiles) {
    foreach ($line in (Read-TextFileUtf8 $envFile) -split "`r?`n") {
        if ($line -match '^\s*(?:#\s*)?([A-Z][A-Z0-9_]{2,})\s*=') {
            [void]$declared.Add($matches[1])
        }
    }
}

if ($envFiles.Count -eq 0) {
    Write-Host 'FAIL: no *.env.example found'
    exit 1
}

# 2. Scan the documentation set.
$docFiles = @()
$rootReadme = Join-Path $repoRoot 'README.md'
if (Test-Path $rootReadme) {
    $docFiles += Get-Item $rootReadme
}

$docsDir = Join-Path $repoRoot 'docs'
if (Test-Path $docsDir) {
    $docFiles += Get-ChildItem -Path $docsDir -Filter '*.md' -File -Recurse
}

foreach ($service in @('frontend', 'application-service', 'agent-service')) {
    $readme = Join-Path (Join-Path $repoRoot $service) 'README.md'
    if (Test-Path $readme) {
        $docFiles += Get-Item $readme
    }
}

$problems = New-Object 'System.Collections.Generic.List[string]'
$seen = New-Object 'System.Collections.Generic.HashSet[string]'

foreach ($file in $docFiles) {
    $relative = $file.FullName.Substring($repoRoot.Length + 1).Replace('\', '/')
    # Archive docs are historical snapshots and may quote renamed keys.
    if ($relative -match '^docs/archive/') {
        continue
    }
    $text = Read-TextFileUtf8 $file

    foreach ($match in [regex]::Matches($text, $keyPattern)) {
        $key = $match.Value
        if ($declared.Contains($key)) {
            continue
        }
        if ($allowedMissing -contains $key) {
            continue
        }
        $dedupeKey = "$relative|$key"
        if ($seen.Add($dedupeKey)) {
            $problems.Add("$relative -> $key")
        }
    }
}

if ($problems.Count -gt 0) {
    Write-Host "FAIL: $($problems.Count) documented keys are missing from *.env.example:"
    foreach ($problem in $problems) {
        Write-Host "  $problem"
    }
    exit 1
}

Write-Host "OK: environment keys in docs all exist in *.env.example ($($docFiles.Count) markdown files, $($declared.Count) declared keys)"
