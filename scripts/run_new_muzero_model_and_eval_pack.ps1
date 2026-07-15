param(
  [string]$Repo = "C:\repos\python\assault",
  [ValidateSet("smoke", "fast", "test", "quality", "dev_plus")]
  [string]$TrainProfile = "quality",
  [string]$ScenarioId = "battaglia_cittadina_2_1",
  [int]$EvalCount = 8,
  [int]$SeedsPerEval = 3,
  [string]$RunsRoot = "runs_curriculum",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [int]$SelfplayWorkers = 1,
  [int]$ReplayCapacityOverride = 16000,
  [int]$SelfplayMaxStepsOverride = 12,
  [int]$MctsSimulationsOverride = 2,
  [int]$MctsInferenceCacheOverride = 65536,
  [int]$HiddenDimOverride = 48,
  [int]$ObservationHeightOverride = 12,
  [int]$ObservationWidthOverride = 12,
  [int]$DynamicsBlocksOverride = 1,
  [int]$PredictionBlocksOverride = 1,
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $trainCfgByProfile = @{
    smoke = "agents/muzero/configs/muzero_config.smoke.yaml"
    fast = "agents/muzero/configs/muzero_config.fast.yaml"
    test = "agents/muzero/configs/muzero_config.test.yaml"
    quality = "agents/muzero/configs/muzero_config.quality.yaml"
    dev_plus = "agents/muzero/configs/muzero_config.dev_plus.yaml"
  }
  $trainCfg = $trainCfgByProfile[$TrainProfile]
  if ([string]::IsNullOrWhiteSpace($trainCfg)) {
    throw "Unsupported TrainProfile: $TrainProfile"
  }

  Write-Host "== 1) Train new MuZero model =="
  .\scripts\run_muzero_train.ps1 -Repo $Repo -Config $trainCfg -MlflowExperiment assault_muzero -MlflowRunName ("pack_" + $TrainProfile + "_" + (Get-Date -Format "yyyyMMdd_HHmmss")) -RunsRoot $RunsRoot -Device $Device -SelfplayWorkers $SelfplayWorkers -ReplayCapacityOverride $ReplayCapacityOverride -SelfplayMaxStepsOverride $SelfplayMaxStepsOverride -MctsSimulationsOverride $MctsSimulationsOverride -MctsInferenceCacheOverride $MctsInferenceCacheOverride -HiddenDimOverride $HiddenDimOverride -ObservationHeightOverride $ObservationHeightOverride -ObservationWidthOverride $ObservationWidthOverride -DynamicsBlocksOverride $DynamicsBlocksOverride -PredictionBlocksOverride $PredictionBlocksOverride
  if ($LASTEXITCODE -ne 0) {
    throw "Train bootstrap step failed with exit code $LASTEXITCODE"
  }

  Write-Host "== 2) Run eval pack on latest model =="
  .\scripts\run_many_evals_latest_muzero.ps1 -Repo $Repo -ScenarioId $ScenarioId -EvalCount $EvalCount -SeedsPerEval $SeedsPerEval -RunsRoot $RunsRoot -Device $Device
  if ($LASTEXITCODE -ne 0) {
    throw "Eval pack step failed with exit code $LASTEXITCODE"
  }

  Write-Host "== 3) Refresh reporting catalog =="
  .\scripts\build_curriculum_reporting_catalog.ps1 -Repo $Repo -RunsRoot $RunsRoot -Out "$RunsRoot/experiments/reporting/model_catalog_latest.json"
  if ($LASTEXITCODE -ne 0) {
    throw "Catalog refresh failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Done."
  Write-Host "Profile: $TrainProfile"
  Write-Host "Scenario: $ScenarioId"
  Write-Host "EvalCount: $EvalCount | SeedsPerEval: $SeedsPerEval"
  Write-Host "Catalog: $RunsRoot\experiments\reporting\model_catalog_latest.json"
  Write-Host "Viewer: http://127.0.0.1:8777/"

  if ($OpenViewer.IsPresent) {
    .\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow -Dev
  }
}
finally {
  Pop-Location
}

