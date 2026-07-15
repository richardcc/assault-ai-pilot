param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.quality.yaml",
  [string]$ModelConfig = "",
  [string]$MlflowExperiment = "",
  [string]$MlflowRunName = ""
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $runsRoot = Join-Path $Repo "runs"
  if (-not (Test-Path $runsRoot)) {
    throw "runs/ not found: $runsRoot"
  }

  $latestEz = Get-ChildItem -Path $runsRoot -Directory -Filter "efficientzero_v2_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  $latestMu = Get-ChildItem -Path $runsRoot -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  $latestRun = $latestEz
  if ($null -eq $latestRun) {
    $latestRun = $latestMu
  }
  if ($null -eq $latestRun) {
    throw "No efficientzero_v2_* or muzero_* run found in $runsRoot"
  }

  $ckptDir = Join-Path $latestRun.FullName "checkpoints"
  if (-not (Test-Path $ckptDir)) {
    throw "Checkpoint directory not found: $ckptDir"
  }

  $latestCkpt = Get-ChildItem -Path $ckptDir -File -Filter "iter_*.pt" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestCkpt) {
    throw "No iter_*.pt found under $ckptDir"
  }

  if ([string]::IsNullOrWhiteSpace($ModelConfig)) {
    if ($latestRun.Name -like "efficientzero_v2_*") {
      $ModelConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.yaml"
    } else {
      $ModelConfig = "agents/muzero/configs/muzero_config.quality.yaml"
    }
  }

  $runId = $latestRun.Name
  Write-Host "== Bench against latest train =="
  Write-Host "Run ID: $runId"
  Write-Host "Checkpoint: $($latestCkpt.FullName)"
  Write-Host "Bench config: $BenchConfig"
  Write-Host "Model config: $ModelConfig"

  $args = @(
    "-m", "assault_bench.runner",
    "--config", $BenchConfig,
    "--checkpoint", $latestCkpt.FullName,
    "--muzero-config", $ModelConfig
  )

  if (-not [string]::IsNullOrWhiteSpace($MlflowExperiment)) {
    $args += @("--mlflow-experiment", $MlflowExperiment)
  }
  if (-not [string]::IsNullOrWhiteSpace($MlflowRunName)) {
    $args += @("--mlflow-run-name", $MlflowRunName)
  }

  python @args
  if ($LASTEXITCODE -ne 0) {
    throw "Benchmark failed with exit code $LASTEXITCODE"
  }

  Write-Host "Done."
  Write-Host "Latest bench: runs\bench_latest.json"
  Write-Host "Bench replay history: runs\$runId\xai\bench_replay_*.json"
}
finally {
  Pop-Location
}
