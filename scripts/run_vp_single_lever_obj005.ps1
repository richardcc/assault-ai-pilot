param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$ScenarioId = "battaglia_cittadina_2_1",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [string]$RunsRoot = "runs_curriculum",
  [int]$EvalCount = 1,
  [int]$SeedsPerEval = 1,
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $common = @{
    Repo = $Repo
    ScenarioId = $ScenarioId
    Device = $Device
    RunsRoot = $RunsRoot
    EvalCount = $EvalCount
    SeedsPerEval = $SeedsPerEval
    SelfplayWorkers = 1
    ReplayCapacityOverride = 16000
    SelfplayMaxStepsOverride = 12
    MctsSimulationsOverride = 2
    MctsInferenceCacheOverride = 65536
    HiddenDimOverride = 48
    ObservationHeightOverride = 12
    ObservationWidthOverride = 12
    DynamicsBlocksOverride = 1
    PredictionBlocksOverride = 1
  }

  Write-Host "== VP single lever A/B: baseline ==" -ForegroundColor Cyan
  .\scripts\run_new_muzero_model_and_eval_pack.ps1 @common -TrainProfile smoke
  if ($LASTEXITCODE -ne 0) {
    throw "Baseline run failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "== VP single lever A/B: objective_loss_weight=0.05 ==" -ForegroundColor Yellow
  .\scripts\run_muzero_train.ps1 `
    -Repo $Repo `
    -Config "agents/muzero/configs/muzero_config.vp_tune_obj_005.yaml" `
    -MlflowExperiment "assault_muzero" `
    -MlflowRunName ("vp_obj005_" + (Get-Date -Format "yyyyMMdd_HHmmss")) `
    -RunsRoot $RunsRoot `
    -Device $Device `
    -SelfplayWorkers 1 `
    -ReplayCapacityOverride 16000 `
    -SelfplayMaxStepsOverride 12 `
    -MctsSimulationsOverride 2 `
    -MctsInferenceCacheOverride 65536 `
    -HiddenDimOverride 48 `
    -ObservationHeightOverride 12 `
    -ObservationWidthOverride 12 `
    -DynamicsBlocksOverride 1 `
    -PredictionBlocksOverride 1
  if ($LASTEXITCODE -ne 0) {
    throw "Objective lever train failed with exit code $LASTEXITCODE"
  }

  .\scripts\run_many_evals_latest_muzero.ps1 `
    -Repo $Repo `
    -ScenarioId $ScenarioId `
    -RunsRoot $RunsRoot `
    -Device $Device `
    -EvalCount $EvalCount `
    -SeedsPerEval $SeedsPerEval `
    -MaxSteps 60 `
    -MctsSimulations 12
  if ($LASTEXITCODE -ne 0) {
    throw "Objective lever eval failed with exit code $LASTEXITCODE"
  }

  .\scripts\build_curriculum_reporting_catalog.ps1 -Repo $Repo -RunsRoot $RunsRoot -Out "$RunsRoot/experiments/reporting/model_catalog_latest.json"
  if ($LASTEXITCODE -ne 0) {
    throw "Catalog refresh failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Done. Compare baseline vs obj005 in viewer (MuZero VPs + Objective Decision Flow)." -ForegroundColor Green
  Write-Host "Catalog: $RunsRoot\experiments\reporting\model_catalog_latest.json"
  Write-Host "Viewer: http://127.0.0.1:8777/"

  if ($OpenViewer.IsPresent) {
    .\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow -Dev -Catalog "$RunsRoot/experiments/reporting/model_catalog_latest.json"
  }
}
finally {
  Pop-Location
}
