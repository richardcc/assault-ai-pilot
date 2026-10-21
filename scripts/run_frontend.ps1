param(
    [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Repo)) {
    $Repo = Split-Path $PSScriptRoot -Parent
}
$Repo = (Resolve-Path $Repo).Path
$UiRoot = Join-Path $Repo "assault_ai_ui"

Push-Location $UiRoot
try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Frontend Simulador Tactico (Vite)     " -ForegroundColor Yellow
    Write-Host " URL: http://localhost:5173/            " -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan

    npm run dev -- --host
}
finally {
    Pop-Location
}
