param(
    [switch]$Reset = $false
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ecosystem = Join-Path $repoRoot "ecosystem.config.cjs"

if (-not (Test-Path $ecosystem)) {
    Write-Error "Missing ecosystem file: $ecosystem"
}

if ($Reset) {
    pm2 delete all | Out-Null
}

Set-Location $repoRoot
pm2 start $ecosystem
pm2 ls
