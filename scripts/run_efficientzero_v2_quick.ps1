param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaseConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.min_valid.yaml",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [int]$Iterations = 8,
  [int]$EpisodesPerIter = 6,
  [int]$TrainUpdatesPerIter = 4,
  [int]$SelfplayWorkers = 1,
  [int]$MctsSimulations = 3,
  [int]$SelfplayMaxSteps = 20,
  [string]$RunsRoot = "runs",
  [switch]$LowMemory,
  [switch]$UseTrackingServer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  # Keep host memory usage bounded (important on Windows + CUDA).
  $env:OMP_NUM_THREADS = "1"
  $env:MKL_NUM_THREADS = "1"
  $env:NUMEXPR_NUM_THREADS = "1"
  $env:OPENBLAS_NUM_THREADS = "1"
  if (-not $UseTrackingServer) {
    # Default to local file-backed MLflow to avoid dependency on a running server.
    Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
  }

  $tmpDir = Join-Path $Repo "runs\experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }
  $cfgPath = Join-Path $Repo $BaseConfig
  if (-not (Test-Path $cfgPath)) {
    throw "Base config not found: $cfgPath"
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $trainCfg = Join-Path $tmpDir ("efficientzero_v2.quick_{0}.yaml" -f $stamp)
  $cfgText = Get-Content -Path $cfgPath -Raw
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
  if ($LowMemory) {
    # End-to-end low-memory profile (host RAM + VRAM safer defaults).
    $EpisodesPerIter = [Math]::Min($EpisodesPerIter, 2)
    $TrainUpdatesPerIter = [Math]::Min($TrainUpdatesPerIter, 2)
    $SelfplayWorkers = 1
    $MctsSimulations = [Math]::Min($MctsSimulations, 2)
    $SelfplayMaxSteps = [Math]::Min($SelfplayMaxSteps, 96)
    if ($cfgText -match "(?m)^\s*batch_size\s*:\s*\d+\s*$") {
      $cfgText = [regex]::Replace($cfgText, "(?m)^\s*batch_size\s*:\s*\d+\s*$", "  batch_size: 8")
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
    if ($cfgText -match "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$") {
      $cfgText = [regex]::Replace($cfgText, "(?m)^\s*episodes_per_iter\s*:\s*\d+\s*$", ("  episodes_per_iter: " + $EpisodesPerIter))
    }
    if ($cfgText -match "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$") {
      $cfgText = [regex]::Replace($cfgText, "(?m)^\s*train_updates_per_iter\s*:\s*\d+\s*$", ("  train_updates_per_iter: " + $TrainUpdatesPerIter))
    }
    if ($cfgText -match "(?m)^\s*num_workers\s*:\s*\d+\s*$") {
      $cfgText = [regex]::Replace($cfgText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $SelfplayWorkers))
    }
    if ($cfgText -match "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$") {
      $cfgText = [regex]::Replace($cfgText, "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$", ("  mcts_simulations: " + $MctsSimulations))
    }
    if ($cfgText -match "(?m)^\s*max_steps\s*:\s*\d+\s*$") {
      $cfgText = [regex]::Replace($cfgText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $SelfplayMaxSteps))
    }
  }
  Set-Content -Path $trainCfg -Value $cfgText -Encoding UTF8

  $runName = ("efficientzero_v2_quick_" + $stamp)
  python -m agents.efficientzero_v2.train.train_efficientzero_v2 --config $trainCfg --mlflow-experiment assault_efficientzero_v2 --mlflow-run-name $runName
  if ($LASTEXITCODE -ne 0) {
    if ($Device -ne "cpu") {
      Write-Warning "EfficientZero v2 failed on device=$Device. Retrying once on CPU."
      $cfgCpuRaw = Get-Content -Path $trainCfg -Raw
      $cpuDeviceRx = [regex]"(?m)^\s*device\s*:\s*.*$"
      $cpuDeviceMatch = $cpuDeviceRx.Match($cfgCpuRaw)
      if ($cpuDeviceMatch.Success) {
        $cfgCpu = $cfgCpuRaw.Remove($cpuDeviceMatch.Index, $cpuDeviceMatch.Length).Insert($cpuDeviceMatch.Index, "  device: cpu")
      } else {
        $cfgCpu = $cfgCpuRaw
      }
      Set-Content -Path $trainCfg -Value $cfgCpu -Encoding UTF8
      python -m agents.efficientzero_v2.train.train_efficientzero_v2 --config $trainCfg --mlflow-experiment assault_efficientzero_v2 --mlflow-run-name ($runName + "_cpu_retry")
      if ($LASTEXITCODE -ne 0) {
        throw "EfficientZero v2 training failed after CPU retry with exit code $LASTEXITCODE"
      }
    } else {
      throw "EfficientZero v2 training failed with exit code $LASTEXITCODE"
    }
  }

  Write-Host "Done. Config: $trainCfg"
}
finally {
  Pop-Location
}

