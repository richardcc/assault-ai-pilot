param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Config = "agents/muzero/configs/muzero_config.dev_plus.yaml",
  [string]$MlflowExperiment = "assault_muzero",
  [string]$MlflowRunName = "",
  [switch]$EnableDiagnostics,
  [string]$RunsRoot = "runs_curriculum",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [int]$SelfplayWorkers = 1,
  [int]$ReplayCapacityOverride = 16000,
  [int]$SelfplayMaxStepsOverride = 12,
  [int]$MctsSimulationsOverride = 2,
  [int]$MctsInferenceCacheOverride = 65536,
  [int]$HiddenDimOverride = 48,
  [int]$ObservationHeightOverride = 12,
  [int]$ObservationWidthOverride = 12,
  [int]$DynamicsBlocksOverride = 1,
  [int]$PredictionBlocksOverride = 1
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Write-Warning "MuZero pipeline is legacy. Preferred pipeline is EfficientZero v2 (scripts/run_efficientzero_v2_quick.ps1)."
  Write-Host "== MuZero training =="
  $tmpDir = Join-Path $Repo "$RunsRoot\experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }
  $configResolved = Join-Path $Repo $Config
  $configWithDiagnostics = Join-Path $tmpDir "muzero_config.train_with_diagnostics.yaml"
  $configText = Get-Content -Path $configResolved -Raw
  $enableDiagnosticsValue = $EnableDiagnostics.IsPresent.ToString().ToLower()
  if ($configText -match "enable_post_train_analytics\s*:") {
    $configText = [regex]::Replace(
      $configText,
      "enable_post_train_analytics\s*:\s*(true|false)",
      ("enable_post_train_analytics: " + $enableDiagnosticsValue)
    )
  } else {
    if ($configText -match "(?m)^train:\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^train:\s*$",
        ("train:`n  enable_post_train_analytics: " + $enableDiagnosticsValue),
        1
      )
    } else {
      $configText = $configText + "`ntrain:`n  enable_post_train_analytics: " + $enableDiagnosticsValue + "`n"
    }
  }
  if ($configText -match "run_root\s*:") {
    $configText = [regex]::Replace(
      $configText,
      "run_root\s*:\s*.*",
      ("run_root: " + $RunsRoot)
    )
  } else {
    $configText = $configText + "`npaths:`n  run_root: " + $RunsRoot + "`n"
  }
  if ($SelfplayWorkers -gt 0) {
    if ($configText -match "(?m)^\s*num_workers\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*num_workers\s*:\s*\d+\s*$",
        ("  num_workers: " + $SelfplayWorkers)
      )
    } elseif ($configText -match "(?m)^selfplay:\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^selfplay:\s*$",
        ("selfplay:`n  num_workers: " + $SelfplayWorkers),
        1
      )
    }
  }
  if ($ReplayCapacityOverride -gt 0) {
    if ($configText -match "(?m)^\s*replay_capacity\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*replay_capacity\s*:\s*\d+\s*$",
        ("  replay_capacity: " + $ReplayCapacityOverride)
      )
    } elseif ($configText -match "(?m)^train:\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^train:\s*$",
        ("train:`n  replay_capacity: " + $ReplayCapacityOverride),
        1
      )
    }
  }
  if ($SelfplayMaxStepsOverride -gt 0) {
    if ($configText -match "(?m)^\s*max_steps\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*max_steps\s*:\s*\d+\s*$",
        ("  max_steps: " + $SelfplayMaxStepsOverride)
      )
    }
  }
  if ($MctsSimulationsOverride -gt 0) {
    if ($configText -match "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*mcts_simulations\s*:\s*\d+\s*$",
        ("  mcts_simulations: " + $MctsSimulationsOverride)
      )
    }
  }
  if ($MctsInferenceCacheOverride -gt 0) {
    if ($configText -match "(?m)^\s*inference_cache_limit\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*inference_cache_limit\s*:\s*\d+\s*$",
        ("  inference_cache_limit: " + $MctsInferenceCacheOverride)
      )
    } elseif ($configText -match "(?m)^selfplay:\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^selfplay:\s*$",
        ("selfplay:`n  inference_cache_limit: " + $MctsInferenceCacheOverride),
        1
      )
    }
  }
  if (-not [string]::IsNullOrWhiteSpace($Device)) {
    if ($configText -match "(?m)^\s*device\s*:\s*.*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*device\s*:\s*.*$",
        ("  device: " + $Device)
      )
    }
  }
  if ($HiddenDimOverride -gt 0) {
    if ($configText -match "(?m)^\s*hidden_dim\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*hidden_dim\s*:\s*\d+\s*$",
        ("  hidden_dim: " + $HiddenDimOverride)
      )
    }
  }
  if ($ObservationHeightOverride -gt 0) {
    if ($configText -match "(?m)^\s*observation_height\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*observation_height\s*:\s*\d+\s*$",
        ("  observation_height: " + $ObservationHeightOverride)
      )
    }
  }
  if ($ObservationWidthOverride -gt 0) {
    if ($configText -match "(?m)^\s*observation_width\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*observation_width\s*:\s*\d+\s*$",
        ("  observation_width: " + $ObservationWidthOverride)
      )
    }
  }
  if ($DynamicsBlocksOverride -gt 0) {
    if ($configText -match "(?m)^\s*dynamics_blocks\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*dynamics_blocks\s*:\s*\d+\s*$",
        ("  dynamics_blocks: " + $DynamicsBlocksOverride)
      )
    }
  }
  if ($PredictionBlocksOverride -gt 0) {
    if ($configText -match "(?m)^\s*prediction_blocks\s*:\s*\d+\s*$") {
      $configText = [regex]::Replace(
        $configText,
        "(?m)^\s*prediction_blocks\s*:\s*\d+\s*$",
        ("  prediction_blocks: " + $PredictionBlocksOverride)
      )
    }
  }
  Set-Content -Path $configWithDiagnostics -Value $configText -Encoding UTF8

  Write-Host "Config: $configWithDiagnostics"
  Write-Host "Device override: $Device"
  Write-Host "Diagnostics enabled: $enableDiagnosticsValue"
  Write-Host "Selfplay workers: $SelfplayWorkers"
  Write-Host "Replay capacity override: $ReplayCapacityOverride"
  Write-Host "Selfplay max_steps override: $SelfplayMaxStepsOverride"
  Write-Host "MCTS simulations override: $MctsSimulationsOverride"
  Write-Host "MCTS inference cache override: $MctsInferenceCacheOverride"
  Write-Host "Hidden dim override: $HiddenDimOverride"
  Write-Host "Observation HxW override: ${ObservationHeightOverride}x${ObservationWidthOverride}"
  Write-Host "Dynamics blocks override: $DynamicsBlocksOverride"
  Write-Host "Prediction blocks override: $PredictionBlocksOverride"
  if ([string]::IsNullOrWhiteSpace($MlflowRunName)) {
    python -m agents.muzero.train.train_muzero --config $configWithDiagnostics --mlflow-experiment $MlflowExperiment
  } else {
    python -m agents.muzero.train.train_muzero --config $configWithDiagnostics --mlflow-experiment $MlflowExperiment --mlflow-run-name $MlflowRunName
  }
  if ($LASTEXITCODE -ne 0) {
    throw "MuZero training failed with exit code $LASTEXITCODE"
  }

  $latestRun = Get-ChildItem -Path (".\" + $RunsRoot) -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestRun) {
    throw "No MuZero run found under .\$RunsRoot"
  }

  $latestCkpt = Get-ChildItem -Path (Join-Path $latestRun.FullName "checkpoints") -File -Filter "iter_*.pt" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run: $($latestRun.Name)"
  if ($null -ne $latestCkpt) {
    Write-Host "Latest checkpoint: $($latestCkpt.FullName)"
  }
  Write-Host "Metrics: $($latestRun.FullName)\metrics\summary.json"
}
finally {
  Pop-Location
}
