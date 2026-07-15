param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaseConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.min_valid.yaml",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [int]$Iterations = 30,
  [int]$EpisodesPerIter = 6,
  [int]$TrainUpdatesPerIter = 4,
  [int]$SelfplayWorkers = 1,
  [int]$MctsSimulations = 3,
  [int]$SelfplayMaxSteps = 112,
  [int]$BenchWorkers = 1,
  [int]$BenchMaxSteps = 40,
  [int[]]$BenchSeeds = @(41, 42),
  [string]$RunsRoot = "runs",
  [switch]$LowMemory
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $env:OMP_NUM_THREADS = "1"
  $env:MKL_NUM_THREADS = "1"
  $env:NUMEXPR_NUM_THREADS = "1"
  $env:OPENBLAS_NUM_THREADS = "1"
  Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue

  $tmpDir = Join-Path $Repo "runs\experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }

  $baseCfgPath = Join-Path $Repo $BaseConfig
  if (-not (Test-Path $baseCfgPath)) {
    throw "Base config not found: $baseCfgPath"
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $trainCfg = Join-Path $tmpDir ("efficientzero_v2.train_bench.quick_{0}.yaml" -f $stamp)
  $benchCfg = Join-Path $tmpDir ("efficientzero_v2.benchmark.quick_{0}.yaml" -f $stamp)

  $cfgText = Get-Content -Path $baseCfgPath -Raw
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*run_root\s*:\s*.*$", ("  run_root: " + $RunsRoot))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*iterations\s*:\s*\d+\s*$", ("  iterations: " + $Iterations))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", ("  episodes_per_iter: " + $EpisodesPerIter))
  if ($cfgText -match "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$", ("  train_updates_per_iter: " + $TrainUpdatesPerIter))
  } else {
    $cfgText = [regex]::Replace(
      $cfgText,
      "(?m)^(\s*episodes_per_iter\s*:\s*\d+\s*)$",
      ('$1' + [Environment]::NewLine + "  train_updates_per_iter: $TrainUpdatesPerIter")
    )
  }
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $SelfplayWorkers))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", ("  mcts_simulations: " + $MctsSimulations))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $SelfplayMaxSteps))
  # Replace only the first device entry (model.device), keep selfplay.device untouched.
  $deviceRx = [regex]"(?m)^\s*device\s*:\s*.*$"
  $deviceMatch = $deviceRx.Match($cfgText)
  if ($deviceMatch.Success) {
    $cfgText = $cfgText.Remove($deviceMatch.Index, $deviceMatch.Length).Insert($deviceMatch.Index, ("  device: " + $Device))
  }
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*enable_post_train_analytics\s*:\s*(true|false)\s*$", "  enable_post_train_analytics: false")

  if ($LowMemory) {
    # End-to-end low-memory profile (host RAM + VRAM safer defaults).
    $EpisodesPerIter = [Math]::Min($EpisodesPerIter, 2)
    $TrainUpdatesPerIter = [Math]::Min($TrainUpdatesPerIter, 2)
    $SelfplayWorkers = 1
    $MctsSimulations = [Math]::Min($MctsSimulations, 2)
    $SelfplayMaxSteps = [Math]::Min($SelfplayMaxSteps, 96)
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*batch_size\s*:\s*\d+\s*$", "  batch_size: 8")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*replay_capacity\s*:\s*\d+\s*$", "  replay_capacity: 1000")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*hidden_dim\s*:\s*\d+\s*$", "  hidden_dim: 48")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*observation_height\s*:\s*\d+\s*$", "  observation_height: 16")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*observation_width\s*:\s*\d+\s*$", "  observation_width: 16")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*dynamics_blocks\s*:\s*\d+\s*$", "  dynamics_blocks: 1")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*prediction_blocks\s*:\s*\d+\s*$", "  prediction_blocks: 1")
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", ("  episodes_per_iter: " + $EpisodesPerIter))
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$", ("  train_updates_per_iter: " + $TrainUpdatesPerIter))
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $SelfplayWorkers))
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", ("  mcts_simulations: " + $MctsSimulations))
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $SelfplayMaxSteps))
  }
  Set-Content -Path $trainCfg -Value $cfgText -Encoding UTF8

  $seedCsv = ($BenchSeeds -join ", ")
  $trainCfgPosix = $trainCfg.Replace("\", "/")
@"
paths:
  run_root: $RunsRoot
  voec_config: voec_sim/configs/voec_config.yaml
  muzero_config: $trainCfgPosix

benchmark:
  device: cuda
  num_workers: $BenchWorkers
  scenario_id: battaglia_cittadina_2_1
  seeds: [$seedCsv]
  max_steps: $BenchMaxSteps
  max_steps_override: 0
  mcts_simulations: $MctsSimulations
  mcts_c_puct: 1.5
  mcts_temperature: 0.45
  matchup_profiles: [muzero_selfplay]
"@ | Set-Content -Path $benchCfg -Encoding UTF8

  Write-Host "== EFFICIENTZERO_V2 QUICK TRAIN =="
  python -m agents.efficientzero_v2.train.train_efficientzero_v2 --config $trainCfg --mlflow-experiment assault_efficientzero_v2 --mlflow-run-name ("efficientzero_v2_train_bench_" + $stamp)
  if ($LASTEXITCODE -ne 0) {
    throw "EfficientZero v2 train failed with exit code $LASTEXITCODE"
  }

  $latestRun = Get-ChildItem -Path (Join-Path $Repo $RunsRoot) -Directory -Filter "efficientzero_v2_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestRun) {
    throw "No EfficientZero v2 run found under $RunsRoot"
  }
  $latestCkpt = Get-ChildItem -Path (Join-Path $latestRun.FullName "checkpoints") -File -Filter "iter_*.pt" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestCkpt) {
    $finalCkptPath = Join-Path $latestRun.FullName "checkpoints\final.pt"
    if (Test-Path $finalCkptPath) {
      $latestCkpt = Get-Item $finalCkptPath
    }
  }
  if ($null -eq $latestCkpt) {
    throw "No checkpoint found for latest run: $($latestRun.Name)"
  }

  Write-Host "== EFFICIENTZERO_V2 QUICK BENCH =="
  python -m assault_bench.runner --config $benchCfg --checkpoint $latestCkpt.FullName --muzero-config $trainCfg --mlflow-experiment assault_bench --mlflow-run-name ("efficientzero_v2_bench_" + $stamp)
  if ($LASTEXITCODE -ne 0) {
    throw "Benchmark failed with exit code $LASTEXITCODE"
  }

  Write-Host "== REFRESH REPORTING CATALOG =="
  python -m mlops.reporting.build_catalog --repo-root . --out "$RunsRoot/experiments/reporting/model_catalog_latest.json" --runs-root $RunsRoot
  if ($LASTEXITCODE -ne 0) {
    throw "Catalog refresh failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run: $($latestRun.Name)"
  Write-Host "Checkpoint: $($latestCkpt.FullName)"
  Write-Host "Bench latest: $RunsRoot\bench_latest.json"
  Write-Host "Catalog: $RunsRoot\experiments\reporting\model_catalog_latest.json"
  Write-Host "Viewer URL: http://127.0.0.1:8777/"
}
finally {
  Pop-Location
}

