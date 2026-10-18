<#
.SYNOPSIS
  Reproduce the entire EfficientZeroV2 Assault training pipeline from Scratch (Zero to Master).

.DESCRIPTION
  This script executes the complete end-to-end curriculum pipeline in a 100% deterministic,
  repeatable sequence without manual intervention:
    Phase A: Foundational 2-Scenario Progressive Curriculum (Phase 1 to Phase 6) starting clean.
    Phase B: Catalog and DuckDB Database Synchronization.
    Phase C: Deep High-Simulation Curriculum (640-800 MCTS sims) with Dynamic Quality Gates.

.PARAMETER Repo
  Repository root path (defaults to current repository root).

.PARAMETER SkipDeepCurriculum
  If set, stops after Phase 6 of the foundational curriculum.

.PARAMETER DryRun
  Validates manifests and configs without launching actual training.
#>
param(
  [string]$Repo = "C:\repos\python\assault",
  [switch]$SkipDeepCurriculum,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host " ASSAULT AI: ZERO-TO-HERO REPRODUCIBILITY PIPELINE (EFFICIENTZERO V2)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host ("Repo root: {0}" -f $Repo)
Write-Host ("DryRun:    {0}" -f $DryRun)
Write-Host ""

Push-Location $Repo
try {
  # -------------------------------------------------------------------------
  # STEP 1: Foundational 2-Scenario Curriculum (Bootstrap -> Self-Play 448 sims)
  # -------------------------------------------------------------------------
  Write-Host ">>> [STEP 1/3] Executing Foundational Curriculum (from Scratch / 0)..." -ForegroundColor Yellow
  $stage1Script = Join-Path $Repo "curriculums\self_vs_self_vs_random_2scenarios_v1\run_all_phases.ps1"
  if (-not (Test-Path $stage1Script)) {
    throw "Stage 1 script not found: $stage1Script"
  }

  $cmd1 = "powershell -ExecutionPolicy Bypass -File `"$stage1Script`" -StopOnPhaseError"
  if ($DryRun) { $cmd1 += " -DryRun" }
  Write-Host ("Executing: {0}" -f $cmd1) -ForegroundColor Gray
  Invoke-Expression $cmd1
  if ($LASTEXITCODE -ne 0) {
    throw "Stage 1 foundational curriculum failed with exit code $LASTEXITCODE."
  }
  Write-Host ">>> [STEP 1/3] Foundational Curriculum completed successfully." -ForegroundColor Green
  Write-Host ""

  # -------------------------------------------------------------------------
  # STEP 2: Catalog Synchronization & DuckDB Ingestion
  # -------------------------------------------------------------------------
  Write-Host ">>> [STEP 2/3] Building & Syncing Reporting Catalog (DuckDB + Parquet)..." -ForegroundColor Yellow
  $stage2Script = Join-Path $Repo "scripts\build_curriculum_reporting_catalog.ps1"
  if (-not (Test-Path $stage2Script)) {
    throw "Stage 2 script not found: $stage2Script"
  }

  $cmd2 = "powershell -ExecutionPolicy Bypass -File `"$stage2Script`""
  Write-Host ("Executing: {0}" -f $cmd2) -ForegroundColor Gray
  Invoke-Expression $cmd2
  if ($LASTEXITCODE -ne 0) {
    throw "Stage 2 catalog synchronization failed with exit code $LASTEXITCODE."
  }
  Write-Host ">>> [STEP 2/3] Catalog and reporting database synchronized." -ForegroundColor Green
  Write-Host ""

  if ($SkipDeepCurriculum) {
    Write-Host "Pipeline finished: Foundational curriculum complete (Deep curriculum skipped by user)." -ForegroundColor Green
    return
  }

  # -------------------------------------------------------------------------
  # STEP 3: Deep Curriculum with Dynamic Quality Gates (640-800 MCTS sims)
  # -------------------------------------------------------------------------
  Write-Host ">>> [STEP 3/3] Executing Deep Curriculum with Dynamic Quality Gates..." -ForegroundColor Yellow
  $stage3Script = Join-Path $Repo "curriculums\self_vs_self_deep_800sims_v1\run_deep_curriculum.ps1"
  if (-not (Test-Path $stage3Script)) {
    throw "Stage 3 script not found: $stage3Script"
  }

  $cmd3 = "powershell -ExecutionPolicy Bypass -File `"$stage3Script`" -ContinueFromLatestCheckpoint -StopOnPhaseError"
  if ($DryRun) { $cmd3 += " -DryRun" }
  Write-Host ("Executing: {0}" -f $cmd3) -ForegroundColor Gray
  Invoke-Expression $cmd3
  if ($LASTEXITCODE -ne 0) {
    throw "Stage 3 deep curriculum failed with exit code $LASTEXITCODE."
  }
  Write-Host ">>> [STEP 3/3] Deep Curriculum completed successfully." -ForegroundColor Green
  Write-Host ""

  Write-Host "==========================================================================" -ForegroundColor Green
  Write-Host " PIPELINE COMPLETE: Model successfully trained from 0 to Deep Mastery!" -ForegroundColor Green
  Write-Host "==========================================================================" -ForegroundColor Green
} finally {
  Pop-Location
}
