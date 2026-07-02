param(
  [string]$Repo = "C:\repos\python\assault",
  [ValidateSet("smoke", "fast", "test", "quality")]
  [string]$Profile = "test",
  [string]$TrainConfig = "",
  [string]$BenchConfig = "",
  [string]$MuZeroConfig = "",
  [int]$CheckpointIter = -1,
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  $totalSw = [System.Diagnostics.Stopwatch]::StartNew()
  $profileConfigs = @{
    smoke = @{
      Train = "agents/muzero/configs/muzero_config.smoke.yaml"
      Bench = "assault_bench/configs/benchmark_config.smoke.yaml"
      MuZero = "agents/muzero/configs/muzero_config.smoke.yaml"
    }
    fast = @{
      Train = "agents/muzero/configs/muzero_config.fast.yaml"
      Bench = "assault_bench/configs/benchmark_config.fast.yaml"
      MuZero = "agents/muzero/configs/muzero_config.fast.yaml"
    }
    test = @{
      Train = "agents/muzero/configs/muzero_config.test.yaml"
      Bench = "assault_bench/configs/benchmark_config.test.yaml"
      MuZero = "agents/muzero/configs/muzero_config.test.yaml"
    }
    quality = @{
      Train = "agents/muzero/configs/muzero_config.quality.yaml"
      Bench = "assault_bench/configs/benchmark_config.quality.yaml"
      MuZero = "agents/muzero/configs/muzero_config.quality.yaml"
    }
  }

  $selected = $profileConfigs[$Profile]
  if ([string]::IsNullOrWhiteSpace($TrainConfig)) { $TrainConfig = $selected.Train }
  if ([string]::IsNullOrWhiteSpace($BenchConfig)) { $BenchConfig = $selected.Bench }
  if ([string]::IsNullOrWhiteSpace($MuZeroConfig)) { $MuZeroConfig = $selected.MuZero }

  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $runsRoot = Join-Path $Repo "runs"
  if (-not (Test-Path $runsRoot)) {
    New-Item -ItemType Directory -Path $runsRoot | Out-Null
  }

  Write-Host "== MuZero training =="
  Write-Host "Profile: $Profile"
  Write-Host "Train config: $TrainConfig"
  $trainSw = [System.Diagnostics.Stopwatch]::StartNew()
  python -m agents.muzero.train.train_muzero --config $TrainConfig
  $trainSw.Stop()
  if ($LASTEXITCODE -ne 0) {
    throw "MuZero training failed with exit code $LASTEXITCODE"
  }
  Write-Host ("Training elapsed: {0:n1}s" -f $trainSw.Elapsed.TotalSeconds)

  $latestRun = Get-ChildItem -Path $runsRoot -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  if ($null -eq $latestRun) {
    throw "No MuZero run directory found under $runsRoot"
  }

  $runId = $latestRun.Name
  $ckptDir = Join-Path $latestRun.FullName "checkpoints"
  if (-not (Test-Path $ckptDir)) {
    throw "Checkpoint directory not found: $ckptDir"
  }
  if ($CheckpointIter -ge 0) {
    $checkpointPath = Join-Path $ckptDir ("iter_{0}.pt" -f $CheckpointIter)
    if (-not (Test-Path $checkpointPath)) {
      throw "Checkpoint not found: $checkpointPath"
    }
  } else {
    $latestCkpt = Get-ChildItem -Path $ckptDir -File -Filter "iter_*.pt" |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($null -eq $latestCkpt) {
      throw "No checkpoint files found under $ckptDir"
    }
    $checkpointPath = $latestCkpt.FullName
  }

  Write-Host "== MuZero benchmark =="
  Write-Host "Bench config: $BenchConfig"
  Write-Host "MuZero config: $MuZeroConfig"
  Write-Host "Run ID: $runId"
  Write-Host "Checkpoint: $checkpointPath"
  $benchSw = [System.Diagnostics.Stopwatch]::StartNew()
  python -m assault_bench.runner --config $BenchConfig --checkpoint $checkpointPath --muzero-config $MuZeroConfig
  $benchSw.Stop()
  if ($LASTEXITCODE -ne 0) {
    throw "MuZero benchmark failed with exit code $LASTEXITCODE"
  }
  Write-Host ("Benchmark elapsed: {0:n1}s" -f $benchSw.Elapsed.TotalSeconds)

  Write-Host ""
  $totalSw.Stop()
  Write-Host ("Total elapsed: {0:n1}s" -f $totalSw.Elapsed.TotalSeconds)
  Write-Host "Done. Run ID: $runId"
  Write-Host "Checkpoint used: $checkpointPath"
  Write-Host "Latest benchmark: runs\bench_latest.json"

  if ($OpenViewer) {
    Write-Host "Opening viewer..."
    python .\scripts\sb3_eval_viewer.py
  }
}
finally {
  Pop-Location
}
