param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Config = "agents/efficientzero_v2/configs/efficientzero_v2_config.q_calib_d_vp_conv.yaml",
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.yaml",
  [string]$MlflowTrainExperiment = "assault_efficientzero_v2",
  [string]$MlflowBenchExperiment = "assault_bench",
  [int]$BenchWorkers = 1,
  [int]$BenchMaxSteps = 80,
  [int[]]$BenchSeeds = @(41, 42, 43)
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runName = "ezv2_q_calib_d_vp_conv_$stamp"
  $runsRoot = Join-Path $Repo "runs"
  if (-not (Test-Path $runsRoot)) {
    New-Item -ItemType Directory -Path $runsRoot -Force | Out-Null
  }

  Write-Host "== TRAIN (EZv2 q_calib_d_vp_conv) =="
  python -m agents.efficientzero_v2.train.train_efficientzero_v2 `
    --config $Config `
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
  $tmpDir = Join-Path $runsRoot "experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }
  $benchCfgTmp = Join-Path $tmpDir ("benchmark.ezv2_q_calib_d_vp_conv.{0}.yaml" -f $stamp)
  $benchText = Get-Content -Path (Join-Path $Repo $BenchConfig) -Raw
  $benchText = [regex]::Replace($benchText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $BenchWorkers))
  $benchText = [regex]::Replace($benchText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $BenchMaxSteps))
  $benchText = [regex]::Replace($benchText, "(?m)^\s*seeds\s*:\s*\[.*\]\s*$", ("  seeds: [" + $seedCsv + "]"))
  Set-Content -Path $benchCfgTmp -Value $benchText -Encoding UTF8

  Write-Host "== BENCH (latest checkpoint) =="
  python -m assault_bench.runner `
    --config $benchCfgTmp `
    --checkpoint $finalCkpt `
    --muzero-config $Config `
    --mlflow-experiment $MlflowBenchExperiment `
    --mlflow-run-name ("bench_" + $runName)
  if ($LASTEXITCODE -ne 0) {
    throw "Bench failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run ID: $($latestRun.Name)"
  Write-Host "Final checkpoint: $finalCkpt"
  Write-Host "Bench latest: runs\bench_latest.json"
}
finally {
  Pop-Location
}
