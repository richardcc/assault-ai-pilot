param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$ScenarioId = "battaglia_cittadina_2_1",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [string]$RunsRoot = "runs_curriculum",
  [int]$EvalCount = 1,
  [int]$SeedsPerEval = 2,
  [int]$SelfplayWorkers = 1,
  [int]$ReplayCapacityOverride = 16000,
  [int]$SelfplayMaxStepsOverride = 24,
  [int]$MctsSimulationsOverride = 8,
  [int]$HiddenDimOverride = 64,
  [int]$ObservationHeightOverride = 16,
  [int]$ObservationWidthOverride = 16,
  [int]$DynamicsBlocksOverride = 2,
  [int]$PredictionBlocksOverride = 1,
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $variants = @(
    @{ Name = "baseline"; Config = "agents/muzero/configs/muzero_config.vp_tune.yaml" },
    @{ Name = "obj005"; Config = "agents/muzero/configs/muzero_config.vp_tune_obj_005.yaml" },
    @{ Name = "obj010"; Config = "agents/muzero/configs/muzero_config.vp_tune_obj_010.yaml" }
  )

  foreach ($v in $variants) {
    Write-Host ""
    Write-Host ("== VP A/B/C variant: {0} ==" -f $v.Name) -ForegroundColor Cyan

    $runName = "vp_capture_{0}_{1}" -f $v.Name, (Get-Date -Format "yyyyMMdd_HHmmss")
    .\scripts\run_muzero_train.ps1 `
      -Repo $Repo `
      -Config $v.Config `
      -MlflowExperiment assault_muzero `
      -MlflowRunName $runName `
      -RunsRoot $RunsRoot `
      -Device $Device `
      -SelfplayWorkers $SelfplayWorkers `
      -ReplayCapacityOverride $ReplayCapacityOverride `
      -SelfplayMaxStepsOverride $SelfplayMaxStepsOverride `
      -MctsSimulationsOverride $MctsSimulationsOverride `
      -HiddenDimOverride $HiddenDimOverride `
      -ObservationHeightOverride $ObservationHeightOverride `
      -ObservationWidthOverride $ObservationWidthOverride `
      -DynamicsBlocksOverride $DynamicsBlocksOverride `
      -PredictionBlocksOverride $PredictionBlocksOverride
    if ($LASTEXITCODE -ne 0) {
      throw ("Training failed for variant {0} with exit code {1}" -f $v.Name, $LASTEXITCODE)
    }

    .\scripts\run_many_evals_latest_muzero.ps1 `
      -Repo $Repo `
      -ScenarioId $ScenarioId `
      -RunsRoot $RunsRoot `
      -Device $Device `
      -EvalCount $EvalCount `
      -SeedsPerEval $SeedsPerEval `
      -MctsSimulations $MctsSimulationsOverride `
      -MaxSteps $SelfplayMaxStepsOverride
    if ($LASTEXITCODE -ne 0) {
      throw ("Eval failed for variant {0} with exit code {1}" -f $v.Name, $LASTEXITCODE)
    }
  }

  Write-Host ""
  Write-Host "VP A/B/C sweep completed." -ForegroundColor Green
  Write-Host ("Catalog: {0}\experiments\reporting\model_catalog_latest.json" -f $RunsRoot)
  Write-Host "Viewer: http://127.0.0.1:8777/"

  if ($OpenViewer.IsPresent) {
    .\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow -Dev -Catalog "$RunsRoot/experiments/reporting/model_catalog_latest.json"
  }
}
finally {
  Pop-Location
}
