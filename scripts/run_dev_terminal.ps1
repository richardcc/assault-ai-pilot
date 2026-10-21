param(
    [string]$Repo = "C:\repos\python\assault",
    [int]$Index = 1
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Repo)) {
    $Repo = Split-Path $PSScriptRoot -Parent
}
$Repo = (Resolve-Path $Repo).Path

Push-Location $Repo
Clear-Host
Write-Host "===================================================" -ForegroundColor Green
Write-Host " Terminal Dev $Index - Entorno .venv Activo        " -ForegroundColor Yellow
Write-Host " Carpeta: $Repo" -ForegroundColor Gray
Write-Host " Listo para ejecutar comandos y scripts             " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Green

if (Test-Path "$Repo\.venv\Scripts\Activate.ps1") {
    . "$Repo\.venv\Scripts\Activate.ps1"
}
python --version
