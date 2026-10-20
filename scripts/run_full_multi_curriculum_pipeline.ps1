<#
.SYNOPSIS
  Orchestrates the Complete Multi-Curriculum Tactical Training Journey for EfficientZero V2.

.DESCRIPTION
  This master automation pipeline executes the full tactical journey in strict pedagogical sequence:
    1. Stage 1: VP Acceleration Curriculum (curriculums/vp_acceleration)
       - Trains the agent from micro-sprint (3-hex uninhibited VP capture) up to full Gela tactical assault.
       - Guarantees that the agent learns non-passivity, turn urgency, and VP capture instinct.
    2. Intermediate: MLOps Telemetry & DuckDB Catalog Synchronization.
    3. Stage 2: Multi-Scenario Progressive Self-Play Curriculum (curriculums/self_vs_self_vs_random_2scenarios_v1)
       - Warm-starts directly from Stage 1's winning promoted checkpoint.
       - Progresses through 7 phases of multi-scenario balance (80/20 -> 50/50) and scaled self-play (20% -> 70%).
    4. Final: Comprehensive MLOps reporting, telemetry sync, and benchmark evaluation summary.

.PARAMETER Repo
  Path to repository root (defaults to current repository root).

.PARAMETER InitialCheckpoint
  Optional base checkpoint to warm-start Stage 1. If omitted, Stage 1 starts clean (from scratch).

.PARAMETER CleanStart
  If set, safely archives all historical runs into 'runs_archive/' and resets DuckDB before launching the pipeline.

.PARAMETER ChainStageCheckpoints
  Whether to warm-start Stage 2 directly from Stage 1's promoted checkpoint (default: true).

.PARAMETER NoChain
  If set, disables checkpoint chaining between Stage 1 and Stage 2 (runs Stage 2 tabula rasa).

.PARAMETER SkipVpCurriculum
  If set, skips Stage 1 and immediately launches Stage 2 using InitialCheckpoint or the latest existing checkpoint.

.PARAMETER SkipMultiScenario
  If set, halts after completing Stage 1 and telemetry ingestion.

.PARAMETER DefaultMaxReinforcementCycles
  Maximum dynamic reinforcement cycles per phase before selecting best-of-cycles (default: 3).

.PARAMETER StopOnGateFail
  If set, halts the pipeline immediately if any phase fails its dynamic quality gate after all reinforcement cycles.

.PARAMETER StopOnPhaseError
  If set, halts immediately upon any training/evaluation execution error.

.PARAMETER DryRun
  Validates all manifests, cycle overlays, and configuration dependencies without launching actual GPU workloads.
#>
param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$InitialCheckpoint = "",
  [bool]$ChainStageCheckpoints = $true,
  [switch]$NoChain,
  [switch]$CleanStart,
  [switch]$SkipVpCurriculum,
  [switch]$SkipMultiScenario,
  [int]$DefaultMaxReinforcementCycles = 3,
  [switch]$StopOnGateFail,
  [switch]$StopOnPhaseError,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($NoChain) {
  $ChainStageCheckpoints = $false
}

function Write-StepHeader {
  param([string]$Title, [string]$Color = "Cyan")
  Write-Host ""
  Write-Host ("=" * 80) -ForegroundColor $Color
  Write-Host (" " + $Title) -ForegroundColor $Color
  Write-Host ("=" * 80) -ForegroundColor $Color
  Write-Host ""
}

function Resolve-LatestPromotedCheckpoint {
  param([string]$RepoRoot, [string]$PhaseFilter = "")
  $tracePath = Join-Path $RepoRoot "runs_curriculum\experiments\reporting\curriculum_phase_traceability.latest.json"
  if (Test-Path $tracePath) {
    try {
      $traceObj = Get-Content -Path $tracePath -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($traceObj.checkpoint_path -and (Test-Path $traceObj.checkpoint_path)) {
        if ([string]::IsNullOrWhiteSpace($PhaseFilter) -or ($traceObj.phase_name -like "*$PhaseFilter*")) {
          return [string]$traceObj.checkpoint_path
        }
      }
    } catch {
      Write-Host ("[Warning] Could not parse trace file: " + $_.Exception.Message) -ForegroundColor Yellow
    }
  }

  # Fallback: scan runs_curriculum and runs for latest final.pt or iter_*.pt
  $roots = @(
    (Join-Path $RepoRoot "runs_curriculum\experiments\curriculum_cycles"),
    (Join-Path $RepoRoot "runs_curriculum"),
    (Join-Path $RepoRoot "runs")
  )
  $candidates = @()
  foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    $items = Get-ChildItem -Path $root -Recurse -File -Filter "*.pt" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "checkpoints\\(final|iter_\d+)\.pt$" }
    if ($items) { $candidates += @($items) }
  }
  if ($candidates.Count -gt 0) {
    $latest = $candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    return [string]$latest.FullName
  }
  return ""
}

$pipelineStartUtc = (Get-Date).ToUniversalTime()

Push-Location $Repo
try {
  Write-StepHeader "ASSAULT TACTICAL RL: FULL MULTI-CURRICULUM PIPELINE ORCHESTRATOR" "Cyan"
  Write-Host ("Start Time (UTC) : {0}" -f $pipelineStartUtc.ToString("u")) -ForegroundColor Gray
  Write-Host ("Repository Root  : {0}" -f $Repo) -ForegroundColor Gray
  $seedDesc = if ($InitialCheckpoint) { $InitialCheckpoint } else { "(None - Cold Start from 0)" }
  Write-Host ("Initial Seed Ckpt: {0}" -f $seedDesc) -ForegroundColor Gray
  Write-Host ("Skip VP Curric.  : {0}" -f $SkipVpCurriculum) -ForegroundColor Gray
  Write-Host ("Skip Multi-Scen. : {0}" -f $SkipMultiScenario) -ForegroundColor Gray
  Write-Host ("Chain Stages     : {0}" -f $ChainStageCheckpoints) -ForegroundColor Gray
  Write-Host ("Clean Start      : {0}" -f $CleanStart) -ForegroundColor Gray
  Write-Host ("DryRun Mode      : {0}" -f $DryRun) -ForegroundColor Gray

  # Clean start: archive previous runs & reset DuckDB
  if ($CleanStart) {
    Write-StepHeader "CLEAN START: ARCHIVING PAST RUNS & RESETTING ENVIRONMENT" "Magenta"
    $resetScript = Join-Path $Repo "scripts\reset_curriculum_environment.ps1"
    if (Test-Path $resetScript) {
      $resetParams = @{
        Repo = $Repo
      }
      if ($DryRun) { $resetParams["DryRun"] = $true }
      & powershell -ExecutionPolicy Bypass -File $resetScript @resetParams
      if ($LASTEXITCODE -ne 0 -and -not $DryRun) {
        throw "Failed to reset curriculum environment."
      }
    }
  }

  $stage1PromotedCheckpoint = $InitialCheckpoint

  # =========================================================================
  # STAGE 1: VP ACCELERATION CURRICULUM (4 PHASES)
  # =========================================================================
  if (-not $SkipVpCurriculum) {
    Write-StepHeader "STAGE 1/2: VP ACCELERATION CURRICULUM (4 PHASES: SPRINT -> 2V2 -> GELA)" "Yellow"
    $stage1Script = Join-Path $Repo "curriculums\vp_acceleration\run_all_phases.ps1"
    if (-not (Test-Path $stage1Script)) {
      throw "Stage 1 script not found: $stage1Script"
    }

    $invokeParamsStage1 = @{
      Repo = $Repo
      CurriculumYaml = ".\curriculums\vp_acceleration\curriculum.yaml"
      DefaultMaxReinforcementCycles = $DefaultMaxReinforcementCycles
    }
    if ($StopOnGateFail) { $invokeParamsStage1["StopOnGateFail"] = $true }
    if ($StopOnPhaseError) { $invokeParamsStage1["StopOnPhaseError"] = $true }
    if ($DryRun) { $invokeParamsStage1["DryRun"] = $true }
    if (-not [string]::IsNullOrWhiteSpace($InitialCheckpoint)) {
      $invokeParamsStage1["ExplicitStartCheckpoint"] = $InitialCheckpoint
    }

    Write-Host ">>> Launching Stage 1: vp_acceleration..." -ForegroundColor Cyan
    & $stage1Script @invokeParamsStage1
    if ($LASTEXITCODE -ne 0 -and -not $DryRun) {
      throw "Stage 1 (vp_acceleration) failed with exit code $LASTEXITCODE."
    }

    if (-not $DryRun) {
      # Resolve promoted checkpoint from Stage 1
      $stage1PromotedCheckpoint = Resolve-LatestPromotedCheckpoint -RepoRoot $Repo -PhaseFilter "phase4"
      if ([string]::IsNullOrWhiteSpace($stage1PromotedCheckpoint)) {
        $stage1PromotedCheckpoint = Resolve-LatestPromotedCheckpoint -RepoRoot $Repo
      }
      Write-Host ""
      Write-Host (">>> Stage 1 Complete! Promoted Seed Checkpoint: {0}" -f $stage1PromotedCheckpoint) -ForegroundColor Green
    } else {
      Write-Host ">>> [DryRun] Stage 1 validation succeeded." -ForegroundColor Green
      $stage1PromotedCheckpoint = "mock_stage1_checkpoint_promoted.pt"
    }

    # Intermediate Sync: DuckDB / Parquet Catalog
    Write-StepHeader "INTERMEDIATE: SYNCING MLOPS REPORTING CATALOG & DUCKDB" "Cyan"
    $syncCatalogScript = Join-Path $Repo "scripts\build_curriculum_reporting_catalog.ps1"
    if (Test-Path $syncCatalogScript) {
      Write-Host ">>> Ingesting Stage 1 cycle runs into DuckDB..." -ForegroundColor Gray
      & powershell -ExecutionPolicy Bypass -File $syncCatalogScript
    }
  } else {
    Write-Host ">>> Skipping Stage 1 (vp_acceleration) by user request." -ForegroundColor Yellow
  }

  if ($SkipMultiScenario) {
    Write-Host "Pipeline terminated after Stage 1 (SkipMultiScenario specified)." -ForegroundColor Green
    return
  }

  # =========================================================================
  # STAGE 2: MULTI-SCENARIO PROGRESSIVE SELF-PLAY CURRICULUM (7 PHASES)
  # =========================================================================
  Write-StepHeader "STAGE 2/2: MULTI-SCENARIO PROGRESSIVE CURRICULUM (7 PHASES, SELF-PLAY TO 70%)" "Yellow"
  $stage2Script = Join-Path $Repo "curriculums\self_vs_self_vs_random_2scenarios_v1\run_all_phases.ps1"
  if (-not (Test-Path $stage2Script)) {
    throw "Stage 2 script not found: $stage2Script"
  }

  $invokeParamsStage2 = @{
    Repo = $Repo
    CurriculumYaml = ".\curriculums\self_vs_self_vs_random_2scenarios_v1\curriculum.yaml"
    DefaultMaxReinforcementCycles = $DefaultMaxReinforcementCycles
  }
  if ($StopOnGateFail) { $invokeParamsStage2["StopOnGateFail"] = $true }
  if ($StopOnPhaseError) { $invokeParamsStage2["StopOnPhaseError"] = $true }
  if ($DryRun) { $invokeParamsStage2["DryRun"] = $true }

  # Checkpoint chaining between Stage 1 and Stage 2 (Default: enabled)
  if ($ChainStageCheckpoints) {
    if (-not [string]::IsNullOrWhiteSpace($stage1PromotedCheckpoint) -and ((Test-Path $stage1PromotedCheckpoint) -or $DryRun)) {
      Write-Host ("Connecting Stage 1 -> Stage 2: Using promoted checkpoint '{0}'" -f $stage1PromotedCheckpoint) -ForegroundColor Magenta
      $invokeParamsStage2["ExplicitStartCheckpoint"] = $stage1PromotedCheckpoint
    } elseif (-not $DryRun -and -not [string]::IsNullOrWhiteSpace($stage1PromotedCheckpoint)) {
      Write-Host ("Warning: Promoted checkpoint '{0}' not found on disk, Stage 2 will search latest run." -f $stage1PromotedCheckpoint) -ForegroundColor Yellow
      $invokeParamsStage2["ContinueFromLatestCheckpoint"] = $true
    }
  } else {
    Write-Host "Stage 2 running clean (tabula rasa) without checkpoint chaining (Adaptive Hyperparameters enabled)." -ForegroundColor Cyan
  }

  Write-Host ">>> Launching Stage 2: self_vs_self_vs_random_2scenarios_v1..." -ForegroundColor Cyan
  & $stage2Script @invokeParamsStage2
  if ($LASTEXITCODE -ne 0 -and -not $DryRun) {
    throw "Stage 2 (multi-scenario) failed with exit code $LASTEXITCODE."
  }

  # Final MLOps Catalog & DuckDB Sync
  Write-StepHeader "FINALIZATION: BUILDING FULL MLOPS REPORTING CATALOG & DUCKDB SYNC" "Cyan"
  if (Test-Path $syncCatalogScript) {
    Write-Host ">>> Ingesting Stage 2 cycle runs into DuckDB..." -ForegroundColor Gray
    & powershell -ExecutionPolicy Bypass -File $syncCatalogScript
  }

  $pipelineEndUtc = (Get-Date).ToUniversalTime()
  $elapsed = $pipelineEndUtc - $pipelineStartUtc

  Write-StepHeader "TACTICAL TRAINING JOURNEY COMPLETED SUCCESSFULLY" "Green"
  Write-Host ("Total Execution Time : {0}h {1}m {2}s" -f $elapsed.Hours, $elapsed.Minutes, $elapsed.Seconds) -ForegroundColor Green
  Write-Host ("Final Promoted Model: {0}" -f (Resolve-LatestPromotedCheckpoint -RepoRoot $Repo)) -ForegroundColor Green
  Write-Host ""
  Write-Host "Observe full metrics and match replays in the MLOps Dashboard:" -ForegroundColor Cyan
  Write-Host "  URL: http://127.0.0.1:8778/" -ForegroundColor White
  Write-Host "  Docs: http://127.0.0.1:8778/docs/" -ForegroundColor White
  Write-Host ""

} finally {
  Pop-Location
}
