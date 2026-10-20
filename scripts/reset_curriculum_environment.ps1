<#
.SYNOPSIS
  Safely archives past training/evaluation runs and resets MLOps reporting state for a clean curriculum run.

.DESCRIPTION
  Moves historical run artifacts from 'runs/' and 'runs_curriculum/' into 'runs_archive/archive_<timestamp>/'
  and refreshes the DuckDB catalog and Parquet indexes to a clean state.
  This allows starting a completely fresh end-to-end curriculum pipeline from 0 without lineage pollution.

.PARAMETER Repo
  Repository root path (defaults to current directory).

.PARAMETER ArchiveDir
  Optional custom directory for archived runs. Defaults to 'runs_archive/archive_<timestamp>'.

.PARAMETER DryRun
  Lists files and directories that would be archived without moving them.
#>
param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$ArchiveDir = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
  if ([string]::IsNullOrWhiteSpace($ArchiveDir)) {
    $ArchiveDir = Join-Path $Repo ("runs_archive\archive_{0}" -f $timestamp)
  }

  Write-Host ""
  Write-Host ("=" * 80) -ForegroundColor Cyan
  Write-Host " RESETTING CURRICULUM TRAINING ENVIRONMENT & ARCHIVING PAST RUNS" -ForegroundColor Cyan
  Write-Host ("=" * 80) -ForegroundColor Cyan
  Write-Host ("Repo Root   : {0}" -f $Repo) -ForegroundColor Gray
  Write-Host ("Archive Dir : {0}" -f $ArchiveDir) -ForegroundColor Gray
  Write-Host ("DryRun Mode : {0}" -f $DryRun) -ForegroundColor Gray
  Write-Host ""

  if (-not $DryRun) {
    New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null
  }

  $itemsToArchive = New-Object System.Collections.Generic.List[string]

  # 1. Collect runs/ contents (train runs, evals)
  $runsPath = Join-Path $Repo "runs"
  if (Test-Path $runsPath) {
    Get-ChildItem -Path $runsPath -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match "^(efficientzero_v2_|muzero_|evals)" } |
      ForEach-Object { $itemsToArchive.Add($_.FullName) }
  }

  # 2. Collect runs_curriculum/ contents
  $runsCurriculumPath = Join-Path $Repo "runs_curriculum"
  if (Test-Path $runsCurriculumPath) {
    Get-ChildItem -Path $runsCurriculumPath -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match "^(efficientzero_v2_|muzero_|evals)" } |
      ForEach-Object { $itemsToArchive.Add($_.FullName) }

    # Experiments: curriculum cycles
    $cyclesPath = Join-Path $runsCurriculumPath "experiments\curriculum_cycles"
    if (Test-Path $cyclesPath) {
      Get-ChildItem -Path $cyclesPath -ErrorAction SilentlyContinue |
        ForEach-Object { $itemsToArchive.Add($_.FullName) }
    }

    # Experiments: runtime configs & manifests
    $runtimeConfigs = Join-Path $runsCurriculumPath "experiments\curriculum_runtime_configs"
    if (Test-Path $runtimeConfigs) {
      Get-ChildItem -Path $runtimeConfigs -ErrorAction SilentlyContinue |
        ForEach-Object { $itemsToArchive.Add($_.FullName) }
    }
    $runtimeManifests = Join-Path $runsCurriculumPath "experiments\curriculum_runtime_manifests"
    if (Test-Path $runtimeManifests) {
      Get-ChildItem -Path $runtimeManifests -ErrorAction SilentlyContinue |
        ForEach-Object { $itemsToArchive.Add($_.FullName) }
    }

    # Traceability files
    $traceDir = Join-Path $runsCurriculumPath "experiments\reporting"
    if (Test-Path $traceDir) {
      Get-ChildItem -Path $traceDir -File -Filter "curriculum_phase_traceability.*" -ErrorAction SilentlyContinue |
        ForEach-Object { $itemsToArchive.Add($_.FullName) }
    }
  }

  Write-Host ("Items found for archiving: {0}" -f $itemsToArchive.Count) -ForegroundColor Yellow
  foreach ($item in $itemsToArchive) {
    $rel = $item.Replace($Repo, "").TrimStart("\/")
    if ($DryRun) {
      Write-Host ("  [DryRun] Would archive: {0}" -f $rel) -ForegroundColor Gray
    } else {
      $destSub = Join-Path $ArchiveDir (Split-Path -Parent $rel)
      New-Item -ItemType Directory -Path $destSub -Force | Out-Null
      try {
        Move-Item -Path $item -Destination $destSub -Force -ErrorAction Stop
        Write-Host ("  Archived: {0}" -f $rel) -ForegroundColor Gray
      } catch {
        # If locked by a running server (e.g. backend / viewer / onnxruntime), copy to archive and leave locked folder
        try {
          Copy-Item -Path $item -Destination $destSub -Recurse -Force -ErrorAction SilentlyContinue
          Write-Host ("  [Warning] In-use by active server, copied to archive: {0}" -f $rel) -ForegroundColor Yellow
        } catch {
          Write-Host ("  [Warning] Could not archive locked item: {0}" -f $rel) -ForegroundColor Yellow
        }
      }
    }
  }

  if (-not $DryRun) {
    Write-Host ""
    Write-Host ">>> Rebuilding clean reporting catalog & DuckDB..." -ForegroundColor Cyan
    $syncCatalogScript = Join-Path $Repo "scripts\build_curriculum_reporting_catalog.ps1"
    if (Test-Path $syncCatalogScript) {
      & powershell -ExecutionPolicy Bypass -File $syncCatalogScript
    }
    Write-Host "Environment successfully reset and clean. Ready for a new run!" -ForegroundColor Green
  } else {
    Write-Host ""
    Write-Host "[DryRun] No files were moved or deleted." -ForegroundColor Yellow
  }
} finally {
  Pop-Location
}
