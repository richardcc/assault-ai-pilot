<#
.SYNOPSIS
  Starts the VP Acceleration Curriculum completely from scratch (Tabula Rasa).

.DESCRIPTION
  1. Stops any existing python training loops.
  2. Archives past runs into 'runs_archive/archive_<timestamp>' and resets the MLOps reporting catalog.
  3. Launches 'run_all_phases.ps1' cleanly starting at Phase 1 without any resume checkpoint.
#>
param(
  [string]$Repo = "C:\repos\python\assault",
  [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"

Set-Location $Repo

Write-Host ""
Write-Host ("=" * 80) -ForegroundColor Cyan
Write-Host " STARTING VP ACCELERATION CURRICULUM FROM SCRATCH (TABULA RASA)" -ForegroundColor Cyan
Write-Host ("=" * 80) -ForegroundColor Cyan
Write-Host ""

# 1. Kill any stray training python processes
Write-Host "[1/3] Ensuring no stray training processes are running..." -ForegroundColor Yellow
$stray = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq "" -and $_.WorkingSet64 -gt 300MB }
if ($stray) {
  $stray | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}
Write-Host "[1/3] Clean." -ForegroundColor Green

# 2. Archive previous runs and reset MLOps catalog
if (-not $SkipArchive) {
  Write-Host "[2/3] Archiving past runs and resetting MLOps catalog..." -ForegroundColor Yellow
  & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $Repo "scripts\reset_curriculum_environment.ps1") -Repo $Repo
  Write-Host "[2/3] Archive complete." -ForegroundColor Green
} else {
  Write-Host "[2/3] Skipping archive step." -ForegroundColor DarkGray
}

# 3. Launch the full curriculum from Phase 1
Write-Host "[3/3] Launching VP Acceleration Curriculum from Phase 1..." -ForegroundColor Yellow
Write-Host "Running: curriculums\vp_acceleration\run_all_phases.ps1" -ForegroundColor Cyan
Write-Host ""

& powershell.exe -ExecutionPolicy Bypass -File (Join-Path $Repo "curriculums\vp_acceleration\run_all_phases.ps1") -Repo $Repo
