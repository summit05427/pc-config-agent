# Validate relative Markdown links inside the repository.
# Usage: powershell -File scripts/check-doc-links.ps1 ; exits 1 when broken links are found.
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path)

# `.trae/skills` bundles third-party skill docs whose example links point at their upstream repo layout.
$markdownFiles = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter *.md |
    Where-Object {
        $_.FullName -notmatch '\\(node_modules|\.venv|target|dist|\.git|\.mypy_cache|\.ruff_cache|\.screenshots)\\' -and
        $_.FullName -notmatch '\\\.trae\\skills\\'
    }

$broken = @()
foreach ($file in $markdownFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
    foreach ($match in [regex]::Matches($content, '\]\(([^)]+)\)')) {
        $target = $match.Groups[1].Value.Trim()
        if ($target -match '^(https?:|mailto:|#|file:)') { continue }
        $path = ($target -split '#')[0]
        if ([string]::IsNullOrWhiteSpace($path)) { continue }
        $resolved = Join-Path $file.DirectoryName ([uri]::UnescapeDataString($path))
        if (-not (Test-Path -LiteralPath $resolved)) {
            $relative = $file.FullName.Substring($Root.Length).TrimStart('\', '/')
            $broken += ($relative + ' -> ' + $target)
        }
    }
}

if ($broken.Count -eq 0) {
    Write-Output ('OK: no broken relative links (' + $markdownFiles.Count + ' markdown files)')
} else {
    $broken | Sort-Object -Unique | ForEach-Object { Write-Output ('BROKEN: ' + $_) }
    exit 1
}
