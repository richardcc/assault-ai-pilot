param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$ScenarioId = "",
  [int]$EvalCount = 8,
  [int]$SeedsPerEval = 2,
  [int]$SeedStart = 1000,
  [int]$MaxSteps = 60,
  [int]$BenchmarkWorkers = 2,
  [int]$MctsSimulations = 12,
  [double]$MctsCPuct = 1.5,
  [double]$MctsTemperature = 0.6,
  [string[]]$MatchupProfiles = @("muzero_selfplay", "muzero_vs_random_side_a", "muzero_vs_random_side_b"),
  [string]$RunsRoot = "runs_curriculum",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cuda",
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $evalCountSafe = [Math]::Max(1, $EvalCount)
  $seedsPerEvalSafe = [Math]::Max(1, $SeedsPerEval)
  $benchmarkWorkersSafe = [Math]::Max(1, $BenchmarkWorkers)
  if ($null -eq $MatchupProfiles -or $MatchupProfiles.Count -eq 0) {
    $MatchupProfiles = @("muzero_selfplay", "muzero_vs_random_side_a", "muzero_vs_random_side_b")
  }
  $profilesCsv = (($MatchupProfiles | ForEach-Object { "'$_'" }) -join ", ")

  $latestRun = Get-ChildItem -Path (".\" + $RunsRoot) -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestRun) {
    throw "No MuZero run found under .\$RunsRoot"
  }

  $ckptDir = Join-Path $latestRun.FullName "checkpoints"
  $latestCkpt = Get-ChildItem -Path $ckptDir -File -Filter "iter_*.pt" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latestCkpt) {
    throw "No checkpoint found in $ckptDir"
  }

  $manifestPath = Join-Path $latestRun.FullName "run_manifest.json"
  if (-not (Test-Path $manifestPath)) {
    throw "Run manifest not found: $manifestPath"
  }
  $manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
  if ([string]::IsNullOrWhiteSpace($ScenarioId)) {
    $ScenarioId = [string]$manifest.scenario_id
  }
  if ([string]::IsNullOrWhiteSpace($ScenarioId)) {
    throw "ScenarioId is empty and could not be inferred from run manifest."
  }

  $cfgModel = $manifest.config.model
  $cfgSelfplay = $manifest.config.selfplay

  $tmpDir = Join-Path $Repo "$RunsRoot\experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }

  $muzeroEvalCfg = Join-Path $tmpDir "muzero_config.eval_many_latest.yaml"
  @"
paths:
  run_root: $RunsRoot
  voec_config: voec_sim/configs/voec_config.yaml

scenario:
  id: $ScenarioId
  seed: 42

model:
  device: $Device
  observation_dim: 4
  encoder_type: $([string]$cfgModel.encoder_type)
  observation_channels: $([int]$cfgModel.observation_channels)
  observation_height: $([int]$cfgModel.observation_height)
  observation_width: $([int]$cfgModel.observation_width)
  hidden_dim: $([int]$cfgModel.hidden_dim)
  dynamics_blocks: $([int]$cfgModel.dynamics_blocks)
  prediction_blocks: $([int]$cfgModel.prediction_blocks)
  action_dim: $([int]$cfgModel.action_dim)
  learning_rate: 0.0005

selfplay:
  num_workers: $([int]$cfgSelfplay.num_workers)
  max_steps: $MaxSteps
  max_steps_override: 0
  mcts_simulations: $([int]$cfgSelfplay.mcts_simulations)
  mcts_c_puct: $([double]$cfgSelfplay.mcts_c_puct)
  mcts_temperature: $([double]$cfgSelfplay.mcts_temperature)
  mcts_unroll_steps: 1
  mcts_discount: 0.997
  timeout_penalty: -0.1

train:
  iterations: 1
  episodes_per_iter: 1
  batch_size: 16
  replay_capacity: 1000
  resume_checkpoint: ""
"@ | Set-Content -Path $muzeroEvalCfg -Encoding UTF8

  Write-Host "== Many evals for latest MuZero run =="
  Write-Host "Run ID: $($latestRun.Name)"
  Write-Host "Scenario: $ScenarioId"
  Write-Host "Checkpoint: $($latestCkpt.FullName)"
  Write-Host "EvalCount: $evalCountSafe | SeedsPerEval: $seedsPerEvalSafe"
  Write-Host "BenchmarkWorkers: $benchmarkWorkersSafe | MatchupProfiles: $($MatchupProfiles -join ', ')"

  for ($i = 0; $i -lt $evalCountSafe; $i++) {
    $seedBase = $SeedStart + ($i * 100)
    $seedList = @()
    for ($j = 0; $j -lt $seedsPerEvalSafe; $j++) {
      $seedList += ($seedBase + $j)
    }
    $seedCsv = ($seedList -join ", ")
    $benchCfg = Join-Path $tmpDir ("benchmark_eval_many_{0}.yaml" -f $i)
    @"
paths:
  run_root: $RunsRoot
  voec_config: voec_sim/configs/voec_config.yaml
  muzero_config: $($muzeroEvalCfg.Replace('\','/'))

benchmark:
  num_workers: $benchmarkWorkersSafe
  scenario_id: $ScenarioId
  seeds: [$seedCsv]
  max_steps: $MaxSteps
  max_steps_override: 0
  mcts_simulations: $MctsSimulations
  mcts_c_puct: $MctsCPuct
  mcts_temperature: $MctsTemperature
  matchup_profiles: [$profilesCsv]
"@ | Set-Content -Path $benchCfg -Encoding UTF8

    $runName = "many_eval_{0}_{1}" -f $i, (Get-Date -Format "HHmmss")
    Write-Host ("- Eval {0}/{1} seeds=[{2}]" -f ($i + 1), $evalCountSafe, $seedCsv)
    python -m assault_bench.runner --config $benchCfg --checkpoint $latestCkpt.FullName --muzero-config $muzeroEvalCfg --mlflow-experiment assault_bench --mlflow-run-name $runName
    if ($LASTEXITCODE -ne 0) {
      throw ("Eval {0} failed with exit code {1}" -f $i, $LASTEXITCODE)
    }
  }

  Write-Host "== Refresh reporting catalog =="
  .\scripts\build_curriculum_reporting_catalog.ps1 -Repo $Repo -RunsRoot $RunsRoot -Out "$RunsRoot/experiments/reporting/model_catalog_latest.json"
  if ($LASTEXITCODE -ne 0) {
    throw "Catalog refresh failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Done."
  Write-Host "Run ID: $($latestRun.Name)"
  Write-Host ("Evals executed: {0}" -f $evalCountSafe)
  Write-Host "Catalog: $RunsRoot\experiments\reporting\model_catalog_latest.json"
  Write-Host "Viewer: http://127.0.0.1:8777/"
  if ($OpenViewer.IsPresent) {
    .\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow -Dev
  }
}
finally {
  Pop-Location
}

