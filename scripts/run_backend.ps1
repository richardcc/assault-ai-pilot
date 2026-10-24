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
    Write-Host " [Backend API Simulator - FastAPI]      " -ForegroundColor Yellow
    Write-Host " URL: http://127.0.0.1:$Port/           " -ForegroundColor Green
    Write-Host " Docs: http://127.0.0.1:$Port/docs      " -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan

    if (Test-Path "$Repo\.venv\Scripts\Activate.ps1") {
        . "$Repo\.venv\Scripts\Activate.ps1"
    }

    Write-Host "[WATCHDOG] Backend auto-restart watchdog enabled." -ForegroundColor DarkCyan
    while ($true) {
        Write-Host "[WATCHDOG] Launching Uvicorn server..." -ForegroundColor Cyan
        try {
            python -m uvicorn assault_backend.main:app --host 127.0.0.1 --port $Port --reload --reload-dir assault_backend --reload-dir assault_model --reload-dir voec_sim
        }
        catch {
            Write-Host "[WATCHDOG] Execution exception: $_" -ForegroundColor Red
        }

        $exitCode = $LASTEXITCODE
        Write-Host "[WATCHDOG] Backend stopped (exit code: $exitCode). Auto-restarting in 2s (Press Ctrl+C to terminate watchdog)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}
finally {
    Pop-Location
}
