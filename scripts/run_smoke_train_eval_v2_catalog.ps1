param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaseConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.min_valid.yaml",
  [string]$RunsRoot = "runs",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cpu"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $tmpDir = Join-Path $Repo "runs\experiments\reporting\tmp_configs"
  New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

  $trainCfg = Join-Path $tmpDir ("ezv2_smoke_train_{0}.yaml" -f $stamp)
  $benchCfg = Join-Path $tmpDir ("ezv2_smoke_bench_{0}.yaml" -f $stamp)

  if (-not (Test-Path $BaseConfig)) {
    throw "Base config not found: $BaseConfig"
  }

  $cfgText = Get-Content -Path $BaseConfig -Raw
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*run_root\s*:\s*.*$", ("  run_root: " + $RunsRoot))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*iterations\s*:\s*\d+\s*$", "  iterations: 1")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", "  episodes_per_iter: 1")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$", "  train_updates_per_iter: 1")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", "  num_workers: 1")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", "  mcts_simulations: 1")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", "  max_steps: 6")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*enable_post_train_analytics\s*:\s*(true|false)\s*$", "  enable_post_train_analytics: false")
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*device\s*:\s*.*$", ("  device: " + $Device), 1)
  Set-Content -Path $trainCfg -Value $cfgText -Encoding UTF8

  $trainCfgPosix = $trainCfg.Replace("\", "/")
@"
paths:
  run_root: $RunsRoot
  voec_config: voec_sim/configs/voec_config.yaml
  muzero_config: $trainCfgPosix

benchmark:
  device: $Device
  num_workers: 1
  scenario_id: battaglia_cittadina_2_1
  seeds: [1]
  max_steps: 6
  max_steps_override: 0
  mcts_simulations: 1
  mcts_c_puct: 1.5
  mcts_temperature: 0.45
  matchup_profiles: [muzero_selfplay]
"@ | Set-Content -Path $benchCfg -Encoding UTF8

  Write-Host "== SMOKE TRAIN (EZV2) =="
  python -m agents.efficientzero_v2.train.train_efficientzero_v2 --config $trainCfg --mlflow-experiment assault_efficientzero_v2 --mlflow-run-name ("ezv2_smoke_train_" + $stamp)
  if ($LASTEXITCODE -ne 0) {
    throw "Smoke train failed with exit code $LASTEXITCODE"
  }

  $latestRun = Get-ChildItem -Path (Join-Path $Repo $RunsRoot) -Directory -Filter "efficientzero_v2_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestRun) {
    throw "No EfficientZero v2 run found under $RunsRoot"
  }

  $finalCkptPath = Join-Path $latestRun.FullName "checkpoints\final.pt"
  if (-not (Test-Path $finalCkptPath)) {
    throw "Final checkpoint not found: $finalCkptPath"
  }

  Write-Host "== SMOKE EVAL/BENCH =="
  python -m assault_bench.runner --config $benchCfg --checkpoint $finalCkptPath --muzero-config $trainCfg --mlflow-experiment assault_bench --mlflow-run-name ("ezv2_smoke_bench_" + $stamp) --device $Device
  if ($LASTEXITCODE -ne 0) {
    throw "Smoke benchmark failed with exit code $LASTEXITCODE"
  }

  $catalogPath = Join-Path $Repo "runs_curriculum\experiments\reporting\model_catalog_latest.json"
  if (-not (Test-Path $catalogPath)) {
    throw "Catalog file not found: $catalogPath"
  }

  $catalog = Get-Content -Path $catalogPath -Raw | ConvertFrom-Json
  if ($catalog.schema_version -ne "reporting_v2_strict") {
    throw "Unexpected schema_version in catalog: $($catalog.schema_version)"
  }
  if ($catalog.catalog_mode -ne "producer_published_strict") {
    throw "catalog_mode is not producer_published_strict: $($catalog.catalog_mode)"
  }

  $runManifestPath = Join-Path $latestRun.FullName "run_manifest.json"
  $metricsSummaryPath = Join-Path $latestRun.FullName "metrics\summary.json"
  $xaiDir = Join-Path $latestRun.FullName "xai"
  $latestBenchEval = Get-ChildItem -Path $xaiDir -File -Filter "bench_eval_*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  Write-Host ""
  Write-Host "Smoke OK."
  Write-Host "Run: $($latestRun.Name)"
  Write-Host "Run dir: $($latestRun.FullName)"
  Write-Host "Checkpoint: $finalCkptPath"
  Write-Host "run_manifest exists: $(Test-Path $runManifestPath)"
  Write-Host "metrics/summary exists: $(Test-Path $metricsSummaryPath)"
  Write-Host "Catalog: $catalogPath"
  Write-Host "catalog.schema_version: $($catalog.schema_version)"
  Write-Host "catalog.catalog_mode: $($catalog.catalog_mode)"
  if ($null -ne $latestBenchEval) {
    Write-Host "Latest bench_eval: $($latestBenchEval.FullName)"
  } else {
    Write-Host "Latest bench_eval: <none>"
  }
  Write-Host ""
  Write-Host "Next recommended gate:"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\gate_reporting_persistence_perf.ps1"
  Write-Host "Full go/no-go:"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\gate_reporting_v2_go_nogo.ps1"
}
finally {
  Pop-Location
}
