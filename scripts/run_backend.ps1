param(
    [string]$Repo = "C:\repos\python\assault",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Repo)) {
    $Repo = Split-Path $PSScriptRoot -Parent
}
$Repo = (Resolve-Path $Repo).Path

Push-Location $Repo
try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " [Backend API Simulador - FastAPI]     " -ForegroundColor Yellow
    Write-Host " URL: http://127.0.0.1:$Port/           " -ForegroundColor Green
    Write-Host " Docs: http://127.0.0.1:$Port/docs      " -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan

    if (Test-Path "$Repo\.venv\Scripts\Activate.ps1") {
        . "$Repo\.venv\Scripts\Activate.ps1"
    }
    python -m uvicorn assault_backend.main:app --host 127.0.0.1 --port $Port --reload
}
finally {
    Pop-Location
}
