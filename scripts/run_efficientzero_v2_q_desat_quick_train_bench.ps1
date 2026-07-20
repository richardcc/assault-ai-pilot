param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Config = "agents/efficientzero_v2/configs/efficientzero_v2_config.q_desat_quick.yaml",
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.smoke.yaml",
  [string]$MlflowTrainExperiment = "assault_efficientzero_v2",
  [string]$MlflowBenchExperiment = "assault_bench",
  [int]$Iterations = 6,
  [int]$EpisodesPerIter = 4,
  [int]$TrainUpdatesPerIter = 3,
  [int]$MctsSimulations = 24,
  [int]$SelfplayMaxSteps = 96,
  [int]$BenchWorkers = 1,
  [int]$BenchMaxSteps = 56,
  [int[]]$BenchSeeds = @(41, 42)
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runName = "ezv2_q_desat_quick_$stamp"
  $runsRoot = Join-Path $Repo "runs"
  if (-not (Test-Path $runsRoot)) {
    New-Item -ItemType Directory -Path $runsRoot -Force | Out-Null
  }

  $tmpDir = Join-Path $runsRoot "experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }

  $trainCfgTmp = Join-Path $tmpDir ("efficientzero_v2.q_desat_quick.train.{0}.yaml" -f $stamp)
  $trainText = Get-Content -Path (Join-Path $Repo $Config) -Raw
  $trainText = [regex]::Replace($trainText, "(?m)^\s*iterations\s*:\s*\d+\s*$", ("  iterations: " + $Iterations))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", ("  episodes_per_iter: " + $EpisodesPerIter))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$", ("  train_updates_per_iter: " + $TrainUpdatesPerIter))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", ("  mcts_simulations: " + $MctsSimulations))
  $trainText = [regex]::Replace($trainText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $SelfplayMaxSteps))
  Set-Content -Path $trainCfgTmp -Value $trainText -Encoding UTF8

  Write-Host "== TRAIN (EZv2 q_desat_quick, short cycle) =="
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

  $seedCsv = ($BenchSeeds -join ", ")
  $benchCfgTmp = Join-Path $tmpDir ("benchmark.ezv2_q_desat_quick.{0}.yaml" -f $stamp)
  $benchText = Get-Content -Path (Join-Path $Repo $BenchConfig) -Raw
  $benchText = [regex]::Replace($benchText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $BenchWorkers))
  $benchText = [regex]::Replace($benchText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $BenchMaxSteps))
  $benchText = [regex]::Replace($benchText, "(?m)^\s*seeds\s*:\s*\[.*\]\s*$", ("  seeds: [" + $seedCsv + "]"))
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

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run ID: $($latestRun.Name)"
  Write-Host "Train config: $trainCfgTmp"
  Write-Host "Final checkpoint: $finalCkpt"
  Write-Host "Bench latest: runs\bench_latest.json"
}
finally {
  Pop-Location
}
