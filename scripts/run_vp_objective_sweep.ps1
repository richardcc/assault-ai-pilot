param(
  [string]$TrackingUri = "http://127.0.0.1:5001",
  [string]$TrainExperiment = "assault_muzero",
  [string]$BenchExperiment = "assault_bench"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:MLFLOW_TRACKING_URI = $TrackingUri

$variants = @(
  @{ Name = "obj005"; Config = "agents/muzero/configs/muzero_config.vp_tune_obj_005.yaml" },
  @{ Name = "obj010"; Config = "agents/muzero/configs/muzero_config.vp_tune_obj_010.yaml" },
  @{ Name = "obj020"; Config = "agents/muzero/configs/muzero_config.vp_tune_obj_020.yaml" }
)

foreach ($v in $variants) {
  $trainRun = "vp_tune_$($v.Name)_train"
  $benchRun = "vp_tune_$($v.Name)_bench"
  Write-Host "=== TRAIN $trainRun ===" -ForegroundColor Cyan
  python -m agents.muzero.train.train_muzero --config $v.Config --mlflow-experiment $TrainExperiment --mlflow-run-name $trainRun

  Write-Host "=== BENCH $benchRun ===" -ForegroundColor Yellow
  python -m assault_bench.runner --config assault_bench/configs/benchmark_config.quality.yaml --checkpoint latest --muzero-config $v.Config --mlflow-experiment $BenchExperiment --mlflow-run-name $benchRun
}

Write-Host "Sweep completado." -ForegroundColor Green
