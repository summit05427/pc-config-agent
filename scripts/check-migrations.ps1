# Verify Flyway migrations under application-service.
#
# Why: a migration that is missing from version control (V6 was once untracked)
# silently diverges between the developer machine and a fresh environment, and
# Flyway then fails with a checksum/version mismatch that is hard to diagnose.
# Checking naming, ordering and git tracking here keeps the history append-only
# and reproducible before it ever reaches a database.
#
# Rules enforced:
#   1. File name matches V<number>__<snake_case>.sql
#   2. Version numbers are unique
#   3. Versions are contiguous from 1 to max (no gaps, no reordering)
#   4. Every migration file is tracked by git
#
# Written for PowerShell 5.1: ASCII-only comments, explicit UTF-8 handling not needed.

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$migrationsRelative = 'application-service/src/main/resources/db/migration'
$migrationsDir = Join-Path $repoRoot $migrationsRelative
$namePattern = '^V(\d+)__([a-z0-9_]+)\.sql$'

if (-not (Test-Path $migrationsDir)) {
    Write-Host "FAIL: migration directory not found: $migrationsRelative"
    exit 1
}

$problems = New-Object 'System.Collections.Generic.List[string]'
$files = @(Get-ChildItem -Path $migrationsDir -Filter '*.sql' -File | Sort-Object Name)
if ($files.Count -eq 0) {
    Write-Host "FAIL: no .sql migrations under $migrationsRelative"
    exit 1
}

$versionToFile = @{}
$maxVersion = 0
foreach ($file in $files) {
    if ($file.Name -notmatch $namePattern) {
        $problems.Add("bad file name (expect V<number>__<snake_case>.sql): $($file.Name)")
        continue
    }
    $version = [int]$matches[1]
    if ($versionToFile.ContainsKey($version)) {
        $problems.Add("duplicate version V$version : $($versionToFile[$version]) and $($file.Name)")
        continue
    }
    $versionToFile[$version] = $file.Name
    if ($version -gt $maxVersion) { $maxVersion = $version }
}

for ($expected = 1; $expected -le $maxVersion; $expected++) {
    if (-not $versionToFile.ContainsKey($expected)) {
        $problems.Add("missing version V$expected (versions must stay contiguous)")
    }
}

# Git tracking check: skipped outside a repository so the script stays usable in
# exported source archives, but CI always runs inside a checkout.
$gitDir = Join-Path $repoRoot '.git'
if (Test-Path $gitDir) {
    $tracked = @(git -C $repoRoot ls-files -- $migrationsRelative)
    if ($LASTEXITCODE -ne 0) {
        $problems.Add('git ls-files failed; cannot verify migration tracking')
    } else {
        $trackedNames = @{}
        foreach ($path in $tracked) {
            $trackedNames[(Split-Path -Leaf $path)] = $true
        }
        foreach ($file in $files) {
            if (-not $trackedNames.ContainsKey($file.Name)) {
                $problems.Add("not tracked by git: $($file.Name)")
            }
        }
    }
} else {
    Write-Host 'NOTE: not a git checkout, skipping tracking check'
}

if ($problems.Count -gt 0) {
    Write-Host "FAIL: $($problems.Count) migration problem(s):"
    foreach ($problem in $problems) {
        Write-Host "  $problem"
    }
    exit 1
}

Write-Host "OK: $($files.Count) migrations valid (V1..V$maxVersion contiguous, all tracked)"
