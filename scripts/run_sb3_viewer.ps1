param(
    [string]$Repo = "C:\repos\python\assault",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Repo)) {
    $Repo = Split-Path $PSScriptRoot -Parent
}
$Repo = (Resolve-Path $Repo).Path

Push-Location $Repo
try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " [Visor Historico SB3 Eval]             " -ForegroundColor Yellow
    Write-Host " URL: http://127.0.0.1:$Port/           " -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan

    if (Test-Path "$Repo\.venv\Scripts\Activate.ps1") {
        . "$Repo\.venv\Scripts\Activate.ps1"
    }
    python scripts/sb3_eval_viewer.py --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
