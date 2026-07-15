param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaseConfig = "agents/muzero/configs/muzero_config.anti_empty_move.yaml",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cpu",
  [int]$Iterations = 1,
  [int]$EpisodesPerIter = 1,
  [int]$SelfplayWorkers = 1,
  [int]$MctsSimulations = 3,
  [int]$SelfplayMaxSteps = 20,
  [int]$BenchWorkers = 1,
  [int]$BenchMaxSteps = 20,
  [int[]]$BenchSeeds = @(41),
  [string]$RunsRoot = "runs",
  [switch]$TrainOnly,
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  # Keep CPU/RAM footprint bounded on local Windows machines.
  $env:OMP_NUM_THREADS = "1"
  $env:MKL_NUM_THREADS = "1"
  $env:NUMEXPR_NUM_THREADS = "1"
  $env:OPENBLAS_NUM_THREADS = "1"

  $tmpDir = Join-Path $Repo "runs_curriculum\experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }

  $baseCfgPath = Join-Path $Repo $BaseConfig
  if (-not (Test-Path $baseCfgPath)) {
    throw "Base config not found: $baseCfgPath"
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $trainCfg = Join-Path $tmpDir ("muzero_config.anti_empty.quick_{0}.yaml" -f $stamp)
  $benchCfg = Join-Path $tmpDir ("benchmark_config.anti_empty.quick_{0}.yaml" -f $stamp)

  if ($IsWindows -and $SelfplayWorkers -gt 1) {
    Write-Warning "Windows shared-memory limitation detected. Forcing SelfplayWorkers=1 (requested $SelfplayWorkers)."
    $SelfplayWorkers = 1
  }

  $cfgText = Get-Content -Path $baseCfgPath -Raw
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*run_root\s*:\s*.*$", ("  run_root: " + $RunsRoot))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*iterations\s*:\s*\d+\s*$", ("  iterations: " + $Iterations))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", ("  episodes_per_iter: " + $EpisodesPerIter))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $SelfplayWorkers))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", ("  mcts_simulations: " + $MctsSimulations))
  if ($cfgText -match "(?m)^\s*max_steps\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $SelfplayMaxSteps))
  }
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*device\s*:\s*.*$", ("  device: " + $Device))
  $cfgText = [regex]::Replace($cfgText, "(?m)^\s*enable_post_train_analytics\s*:\s*(true|false)\s*$", "  enable_post_train_analytics: false")
  if ($cfgText -match "(?m)^\s*batch_size\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*batch_size\s*:\s*\d+\s*$", "  batch_size: 16")
  }
  if ($cfgText -match "(?m)^\s*replay_capacity\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*replay_capacity\s*:\s*\d+\s*$", "  replay_capacity: 1000")
  }
  if ($cfgText -match "(?m)^\s*hidden_dim\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*hidden_dim\s*:\s*\d+\s*$", "  hidden_dim: 48")
  }
  if ($cfgText -match "(?m)^\s*observation_height\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*observation_height\s*:\s*\d+\s*$", "  observation_height: 16")
  }
  if ($cfgText -match "(?m)^\s*observation_width\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*observation_width\s*:\s*\d+\s*$", "  observation_width: 16")
  }
  if ($cfgText -match "(?m)^\s*dynamics_blocks\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*dynamics_blocks\s*:\s*\d+\s*$", "  dynamics_blocks: 1")
  }
  if ($cfgText -match "(?m)^\s*prediction_blocks\s*:\s*\d+\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*prediction_blocks\s*:\s*\d+\s*$", "  prediction_blocks: 1")
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

  Write-Host "== QUICK TRAIN (anti-empty-move) =="
  Write-Host "Train config: $trainCfg"
  Write-Host "Requested device: $Device"
  Write-Host "Effective device line:"
  Select-String -Path $trainCfg -Pattern "^\s*device\s*:" | ForEach-Object { Write-Host ("  " + $_.Line.Trim()) }
  $runName = ("anti_empty_quick_" + $stamp)
  python -m agents.muzero.train.train_muzero --config $trainCfg --mlflow-experiment assault_muzero --mlflow-run-name $runName
  if ($LASTEXITCODE -ne 0) {
    if ($Device -ne "cpu") {
      Write-Warning "Training failed on device=$Device. Retrying once on CPU."
      $cfgCpu = [regex]::Replace((Get-Content -Path $trainCfg -Raw), "(?m)^\s*device\s*:\s*.*$", "  device: cpu")
      Set-Content -Path $trainCfg -Value $cfgCpu -Encoding UTF8
      Select-String -Path $trainCfg -Pattern "^\s*device\s*:" | ForEach-Object { Write-Host ("  retry " + $_.Line.Trim()) }
      python -m agents.muzero.train.train_muzero --config $trainCfg --mlflow-experiment assault_muzero --mlflow-run-name ($runName + "_cpu_retry")
      if ($LASTEXITCODE -ne 0) {
        throw "Training failed after CPU retry with exit code $LASTEXITCODE"
      }
    } else {
      throw "Training failed with exit code $LASTEXITCODE"
    }
  }

  $latestRun = Get-ChildItem -Path (Join-Path $Repo $RunsRoot) -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestRun) {
    throw "No MuZero run found under $RunsRoot"
  }
  $latestCkpt = Get-ChildItem -Path (Join-Path $latestRun.FullName "checkpoints") -File -Filter "iter_*.pt" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestCkpt) {
    throw "No checkpoint found for latest run: $($latestRun.Name)"
  }

  if ($TrainOnly) {
    Write-Host "TrainOnly enabled: skipping benchmark and catalog refresh."
  } else {
    Write-Host "== QUICK BENCH =="
    Write-Host "Bench config: $benchCfg"
    Write-Host "Checkpoint: $($latestCkpt.FullName)"
    python -m assault_bench.runner --config $benchCfg --checkpoint $latestCkpt.FullName --muzero-config $trainCfg --mlflow-experiment assault_bench --mlflow-run-name ("anti_empty_quick_bench_" + $stamp)
    if ($LASTEXITCODE -ne 0) {
      throw "Benchmark failed with exit code $LASTEXITCODE"
    }

    Write-Host "== REFRESH REPORTING CATALOG =="
    .\scripts\build_curriculum_reporting_catalog.ps1 -Repo $Repo -RunsRoot $RunsRoot -Out "$RunsRoot/experiments/reporting/model_catalog_latest.json"
    if ($LASTEXITCODE -ne 0) {
      throw "Catalog refresh failed with exit code $LASTEXITCODE"
    }
  }

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run: $($latestRun.Name)"
  Write-Host "Checkpoint: $($latestCkpt.FullName)"
  Write-Host "Bench latest: $RunsRoot\bench_latest.json"
  Write-Host "Catalog: $RunsRoot\experiments\reporting\model_catalog_latest.json"
  Write-Host "Viewer URL: http://127.0.0.1:8777/"

  if ($OpenViewer) {
    .\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow -Dev -Catalog "$RunsRoot/experiments/reporting/model_catalog_latest.json"
  }
}
finally {
  Pop-Location
}

