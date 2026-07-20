param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Config = "agents/efficientzero_v2/configs/efficientzero_v2_config.vp_push_aggressive.yaml",
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.yaml",
  [string]$MlflowTrainExperiment = "assault_efficientzero_v2",
  [string]$MlflowBenchExperiment = "assault_bench",
  [int]$Iterations = 50,
  [int]$EpisodesPerIter = 20,
  [int]$TrainUpdatesPerIter = 3,
  [int]$MctsSimulations = 24,
  [int]$SelfplayMaxSteps = 96,
  [int]$BenchWorkers,
  [int]$BenchMaxSteps,
  [int[]]$BenchSeeds
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runName = "ezv2_vp_push_aggressive_$stamp"
  $runsRoot = Join-Path $Repo "runs"
  if (-not (Test-Path $runsRoot)) {
    New-Item -ItemType Directory -Path $runsRoot -Force | Out-Null
  }

  $tmpDir = Join-Path $runsRoot "experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }

  $trainCfgTmp = Join-Path $tmpDir ("efficientzero_v2.vp_push_aggressive.train.{0}.yaml" -f $stamp)
  $trainText = Get-Content -Path (Join-Path $Repo $Config) -Raw
  $trainText = [regex]::Replace($trainText, "(?m)^\s*iterations\s*:\s*\d+\s*$", ("  iterations: " + $Iterations))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", ("  episodes_per_iter: " + $EpisodesPerIter))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$", ("  train_updates_per_iter: " + $TrainUpdatesPerIter))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", ("  mcts_simulations: " + $MctsSimulations))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $SelfplayMaxSteps))
  Set-Content -Path $trainCfgTmp -Value $trainText -Encoding UTF8

  Write-Host "== TRAIN (EZv2 vp_push_aggressive, default cycle) =="
  python -m agents.efficientzero_v2.train.train_efficientzero_v2 `
    --config $trainCfgTmp `
    --mlflow-experiment $MlflowTrainExperiment `
    --mlflow-run-name $runName
  if ($LASTEXITCODE -ne 0) {
    throw "Train failed with exit code $LASTEXITCODE"
  }

  $latestRun = Get-ChildItem -Path $runsRoot -Directory -Filter "efficientzero_v2_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestRun) {
    throw "No efficientzero_v2_* run directory found under $runsRoot"
  }

  $finalCkpt = Join-Path $latestRun.FullName "checkpoints\final.pt"
  if (-not (Test-Path $finalCkpt)) {
    throw "Final checkpoint not found: $finalCkpt"
  }

  $benchCfgTmp = Join-Path $tmpDir ("benchmark.ezv2_vp_push_aggressive.{0}.yaml" -f $stamp)
  $benchText = Get-Content -Path (Join-Path $Repo $BenchConfig) -Raw
  if ($PSBoundParameters.ContainsKey("BenchWorkers")) {
    $benchText = [regex]::Replace($benchText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $BenchWorkers))
  }
  if ($PSBoundParameters.ContainsKey("BenchMaxSteps")) {
    $benchText = [regex]::Replace($benchText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $BenchMaxSteps))
  }
  if ($PSBoundParameters.ContainsKey("BenchSeeds")) {
    $seedCsv = ($BenchSeeds -join ", ")
    $benchText = [regex]::Replace($benchText, "(?m)^\s*seeds\s*:\s*\[.*\]\s*$", ("  seeds: [" + $seedCsv + "]"))
  }
  Set-Content -Path $benchCfgTmp -Value $benchText -Encoding UTF8

  Write-Host "== BENCH (latest checkpoint) =="
  python -m assault_bench.runner `
    --config $benchCfgTmp `
    --checkpoint $finalCkpt `
    --muzero-config $trainCfgTmp `
    --mlflow-experiment $MlflowBenchExperiment `
    --mlflow-run-name ("bench_" + $runName)
  if ($LASTEXITCODE -ne 0) {
    throw "Bench failed with exit code $LASTEXITCODE"
  }

  Write-Host "== REPORTING CATALOG =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\build_curriculum_reporting_catalog.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Catalog build failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run ID: $($latestRun.Name)"
  Write-Host "Train config: $trainCfgTmp"
  Write-Host "Final checkpoint: $finalCkpt"
  Write-Host "Bench latest: runs\bench_latest.json"
  Write-Host "Catalog: runs\experiments\reporting\catalog\catalog_latest.json"
}
finally {
  Pop-Location
}
