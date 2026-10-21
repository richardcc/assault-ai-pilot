param(
    [string]$Repo = "C:\repos\python\assault",
    [int]$Port = 8780,
    [switch]$OpenWindow
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Repo)) {
    $Repo = $PSScriptRoot
    if (-not (Test-Path (Join-Path $Repo "tools\unit_editor_server.py"))) {
        $Repo = Split-Path $PSScriptRoot -Parent
    }
}
$Repo = (Resolve-Path $Repo).Path

Push-Location $Repo
try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Assault Unit & Formation Editor       " -ForegroundColor Yellow
    Write-Host " URL: http://127.0.0.1:$Port/           " -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan

    $py = if (Test-Path "$Repo\.venv\Scripts\python.exe") { "$Repo\.venv\Scripts\python.exe" } else { "python" }
    if (Test-Path "$Repo\.venv\Scripts\Activate.ps1") {
        . "$Repo\.venv\Scripts\Activate.ps1"
    }

    if ($OpenWindow) {
        Start-Process "http://127.0.0.1:$Port/"
    }

    & $py tools/unit_editor_server.py --port $Port
}
finally {
    Pop-Location
}
