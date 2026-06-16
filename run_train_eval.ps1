# run_train_eval.ps1
# Uso:
#   .\run_train_eval.ps1
#   .\run_train_eval.ps1 -RepoPath "C:\repos\python\assault"
#   .\run_train_eval.ps1 -SkipTrain -Seeds 42,43,44 -Episodes 100
#   .\run_train_eval.ps1 -OutDir "C:\tmp\sb3_eval\run_custom"
#   .\run_train_eval.ps1 -AutoGateAndPromoteBaseline

[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int[]]$Seeds = @(42, 43, 44),
  [int]$Episodes = 100,
  [switch]$SkipTrain,
  [string]$OutDir,
  [switch]$ContinueOnEvalError,
  [switch]$ParallelEvalSeeds,
  [int]$EvalParallelJobs = 2,
  [switch]$AutoGateAndPromoteBaseline,
  [switch]$AutoCompareAgainstBaseline,
  [switch]$FailOnCompareNoGo,
  [string]$BaselineRootDir = "",
  [string]$CompareBaselineReportPath = "",
  [double]$GateTrueWinRateMin = 0.10,
  [double]$GateLossRateMax = 0.60,
  [double]$GateStrategyStuckMax = 0.70,
  [double]$GateVpEntryMissedMax = 1.00,
  [double]$GatePositionReversalMax = 0.05,
  [int]$GateCaptured45MinEpisodes = 1,
  [double]$CompareTrueWinRateDeltaMin = -0.10,
  [int]$CompareCaptured45DeltaMin = -5,
  [double]$CompareVpEntryMissedDeltaMax = 0.15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
  param(
    [string]$Message,
    [string]$FilePath
  )
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$ts] $Message" | Tee-Object -FilePath $FilePath -Append
}

function Run-Step {
  param(
    [string]$Title,
    [string[]]$Command,
    [string]$FilePath,
    [string]$HeartbeatPath
  )

  Write-Log "==== $Title ====" $FilePath
  Write-Log ("CMD: " + ($Command -join " ")) $FilePath
  $startedAt = Get-Date
  Set-Content -Path $HeartbeatPath -Value ("status=running`nstep={0}`nstarted_at={1}`nlast_update={1}`nelapsed_seconds=0" -f $Title, ($startedAt.ToString("s")))

  $hbJob = Start-Job -ScriptBlock {
    param($Path, $Step, $StartText)
    $start = [datetime]::Parse($StartText)
    while ($true) {
      $now = Get-Date
      $elapsed = [int]([timespan]($now - $start)).TotalSeconds
      $content = @(
        "status=running"
        "step=$Step"
        "started_at=$StartText"
        ("last_update=" + $now.ToString("s"))
        "elapsed_seconds=$elapsed"
      ) -join [Environment]::NewLine
      Set-Content -Path $Path -Value $content
      Start-Sleep -Seconds 15
    }
  } -ArgumentList $HeartbeatPath, $Title, $startedAt.ToString("s")

  try {
    # Native Python stderr lines should be logged fully (no early Stop on first stderr line).
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Command[0] $Command[1..($Command.Length - 1)] 2>&1 | Tee-Object -FilePath $FilePath -Append
    $ErrorActionPreference = $prevEap
    if ($LASTEXITCODE -ne 0) {
      throw "Fallo en paso: $Title (exit=$LASTEXITCODE)"
    }
    $doneAt = Get-Date
    $elapsedDone = [int]([timespan]($doneAt - $startedAt)).TotalSeconds
    Set-Content -Path $HeartbeatPath -Value ("status=done`nstep={0}`nstarted_at={1}`nlast_update={2}`nelapsed_seconds={3}" -f $Title, $startedAt.ToString("s"), $doneAt.ToString("s"), $elapsedDone)
  }
  catch {
    # Restore preference in case of early throw.
    $ErrorActionPreference = "Stop"
    $errAt = Get-Date
    $elapsedErr = [int]([timespan]($errAt - $startedAt)).TotalSeconds
    $msg = $_.Exception.Message -replace "`r|`n", " "
    $detail = ($_ | Out-String).Trim()
    Set-Content -Path $HeartbeatPath -Value ("status=error`nstep={0}`nstarted_at={1}`nlast_update={2}`nelapsed_seconds={3}`nerror={4}" -f $Title, $startedAt.ToString("s"), $errAt.ToString("s"), $elapsedErr, $msg)
    if (-not [string]::IsNullOrWhiteSpace($detail)) {
      Write-Log ("ERROR detail: {0}" -f $detail) $FilePath
    }
    throw
  }
  finally {
    if ($hbJob) {
      Stop-Job -Job $hbJob -ErrorAction SilentlyContinue | Out-Null
      Remove-Job -Job $hbJob -ErrorAction SilentlyContinue | Out-Null
    }
  }
}

function Get-GateMetricsFromReport {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ReportPath
  )
  $raw = Get-Content -Path $ReportPath -Raw | ConvertFrom-Json
  $rlSide = $null
  if ($raw.meta -and $raw.meta.rl_sides -and $raw.meta.rl_sides.Count -gt 0) {
    $rlSide = [string]$raw.meta.rl_sides[0]
  }
  if ([string]::IsNullOrWhiteSpace($rlSide)) {
    throw "No RL side found in report metadata: $ReportPath"
  }
  $sideNode = $raw.by_side_and_scenario.$rlSide
  if (-not $sideNode) {
    throw "Report missing by_side_and_scenario for side '$rlSide': $ReportPath"
  }
  $scenarioNames = @($sideNode.PSObject.Properties.Name)
  if ($scenarioNames.Count -lt 1) {
    throw "Report missing scenarios for side '$rlSide': $ReportPath"
  }
  $scenario = [string]$scenarioNames[0]
  $scenarioNode = $sideNode.$scenario
  $summary = $scenarioNode.summary
  $mission = $scenarioNode.mission
  $captured = $summary.captured_final_counts
  $capt4 = 0
  $capt5 = 0
  if ($captured) {
    if ($captured.PSObject.Properties.Name -contains "4") { $capt4 = [int]$captured."4" }
    if ($captured.PSObject.Properties.Name -contains "5") { $capt5 = [int]$captured."5" }
  }
  [pscustomobject]@{
    rl_side                = $rlSide
    scenario               = $scenario
    true_win_rate          = [double]$summary.true_win_rate
    loss_rate              = [double]$summary.loss_rate
    strategy_stuck_ratio   = [double]$mission.strategy_stuck_ratio
    vp_entry_missed_rate   = [double]$mission.vp_entry_missed_rate
    position_reversal_rate = [double]$mission.position_reversal_rate
    captured_4_5_episodes  = [int]($capt4 + $capt5)
  }
}

function Evaluate-Gate {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$Metrics,
    [double]$TrueWinMin,
    [double]$LossMax,
    [double]$StrategyStuckMax,
    [double]$VpEntryMissedMax,
    [double]$PositionReversalMax,
    [int]$Captured45Min
  )
  $checks = [ordered]@{
    true_win_rate_min        = ($Metrics.true_win_rate -ge $TrueWinMin)
    loss_rate_max            = ($Metrics.loss_rate -le $LossMax)
    strategy_stuck_max       = ($Metrics.strategy_stuck_ratio -le $StrategyStuckMax)
    vp_entry_missed_max      = ($Metrics.vp_entry_missed_rate -lt $VpEntryMissedMax)
    position_reversal_max    = ($Metrics.position_reversal_rate -le $PositionReversalMax)
    captured_4_5_min_episode = ($Metrics.captured_4_5_episodes -ge $Captured45Min)
  }
  $failed = @($checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
  [pscustomobject]@{
    passed_all = ($failed.Count -eq 0)
    failed_checks = $failed
    checks = $checks
  }
}

function Subtract-Num {
  param(
    $Left,
    $Right
  )
  $l = if ($null -eq $Left) { 0.0 } else { [double]$Left }
  $r = if ($null -eq $Right) { 0.0 } else { [double]$Right }
  return ($l - $r)
}

function Evaluate-CompareGate {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$GoodMetrics,
    [Parameter(Mandatory = $true)]
    [pscustomobject]$BadMetrics,
    [double]$TrueWinRateDeltaMin,
    [int]$Captured45DeltaMin,
    [double]$VpEntryMissedDeltaMax
  )
  $deltas = [ordered]@{
    true_win_rate_delta = (Subtract-Num -Left $BadMetrics.true_win_rate -Right $GoodMetrics.true_win_rate)
    captured_4_5_delta = [int](Subtract-Num -Left $BadMetrics.captured_4_5_episodes -Right $GoodMetrics.captured_4_5_episodes)
    vp_entry_missed_rate_delta = (Subtract-Num -Left $BadMetrics.vp_entry_missed_rate -Right $GoodMetrics.vp_entry_missed_rate)
  }
  $checks = [ordered]@{
    true_win_rate_delta_min_ok = ($deltas.true_win_rate_delta -gt $TrueWinRateDeltaMin)
    captured_4_5_delta_min_ok = ($deltas.captured_4_5_delta -gt $Captured45DeltaMin)
    vp_entry_missed_rate_delta_max_ok = ($deltas.vp_entry_missed_rate_delta -lt $VpEntryMissedDeltaMax)
  }
  $failed = @($checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
  [pscustomobject]@{
    passed_all = ($failed.Count -eq 0)
    failed_checks = $failed
    deltas = $deltas
    checks = $checks
  }
}

function Resolve-BaselineReportPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [string]$ExplicitPath
  )
  if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
    if (-not (Test-Path -Path $ExplicitPath -PathType Leaf)) {
      throw "Baseline report not found: $ExplicitPath"
    }
    return $ExplicitPath
  }

  $latestPointer = Join-Path $RepoRoot "artifacts\baselines\LATEST_BASELINE.txt"
  if (-not (Test-Path -Path $latestPointer -PathType Leaf)) {
    throw "CompareBaselineReportPath is empty and baseline pointer not found: $latestPointer"
  }
  $baselineDir = (Get-Content -Path $latestPointer -Raw).Trim()
  if ([string]::IsNullOrWhiteSpace($baselineDir)) {
    throw "Baseline pointer is empty: $latestPointer"
  }
  if (-not (Test-Path -Path $baselineDir -PathType Container)) {
    throw "Baseline directory from pointer does not exist: $baselineDir"
  }

  $baselineReports = @(
    Get-ChildItem -Path $baselineDir -Filter "metrics_sb3_report_*.json" -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending
  )
  if ($baselineReports.Count -lt 1) {
    throw "No metrics_sb3_report_*.json found in baseline directory: $baselineDir"
  }
  return $baselineReports[0].FullName
}

function Promote-BaselineArtifacts {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$RunDir,
    [Parameter(Mandatory = $true)]
    [string]$ReportPath,
    [Parameter(Mandatory = $true)]
    [string]$RlSide,
    [string]$BaselineRoot
  )
  $root = $BaselineRoot
  if ([string]::IsNullOrWhiteSpace($root)) {
    $root = Join-Path $RepoRoot "artifacts\baselines"
  }
  New-Item -ItemType Directory -Force -Path $root | Out-Null
  $runName = Split-Path -Leaf $RunDir
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $target = Join-Path $root ("{0}_{1}" -f $runName, $stamp)
  New-Item -ItemType Directory -Force -Path $target | Out-Null

  $modelPath = Join-Path $RepoRoot ("models\sb3_latest_{0}.zip" -f $RlSide)
  $vecPath = Join-Path $RepoRoot ("models\sb3_vecnormalize_{0}.pkl" -f $RlSide)
  $metaPath = Join-Path $RepoRoot ("models\sb3_latest_{0}.meta.json" -f $RlSide)
  $cfgPath = Join-Path $RepoRoot "assault_sim\config\train_config.json"

  foreach ($path in @($modelPath, $vecPath, $metaPath, $cfgPath, $ReportPath)) {
    if (-not (Test-Path $path)) {
      throw "Cannot promote baseline; required artifact missing: $path"
    }
    Copy-Item -Path $path -Destination $target -Force
  }
  Set-Content -Path (Join-Path $root "LATEST_BASELINE.txt") -Value $target
  return $target
}

function Test-ObsShapeCompatibility {
  param(
    [string]$RepoRoot,
    [string]$LogPath
  )
  $probe = @"
from pathlib import Path
import numpy as np
from stable_baselines3 import PPO
from assault_sim.config.train_config import load_train_config
from assault_sim.envs.gym_assault_env import GymAssaultEnv
from assault_sim.evaluation.eval_sb3 import _resolve_model_path_for_side

repo = Path(r"$RepoRoot")
cfg = load_train_config(repo / "assault_sim" / "config" / "train_config.json")
side = (list(getattr(cfg, "rl_sides", [])) or [getattr(cfg, "rl_side", "US")])[0]
scenario = (list(getattr(cfg, "scenario_schedule", []))[0].id if getattr(cfg, "scenario_schedule", None) else str(getattr(cfg, "scenario", "")))
model_path = _resolve_model_path_for_side(repo, side)
if model_path is None:
    print("precheck: model not found -> skip")
    raise SystemExit(0)
model = PPO.load(str(model_path), device="cpu")
env = GymAssaultEnv(scenario=scenario, rl_side=side, seed=int(getattr(cfg, "seed", 42)))
obs, _ = env.reset()
model_shape = tuple(getattr(getattr(model, "observation_space", None), "shape", ()) or ())
env_shape = tuple(np.asarray(obs, dtype=np.float32).shape)
print(f"precheck: model_obs_shape={model_shape} env_obs_shape={env_shape}")
raise SystemExit(0 if model_shape == env_shape else 3)
"@
  Write-Log "Running precheck: model/env observation shape compatibility" $LogPath
  $tmp = Join-Path $env:TEMP "assault_obs_shape_precheck.py"
  Set-Content -Path $tmp -Value $probe -Encoding UTF8
  & python $tmp 2>&1 | Tee-Object -FilePath $LogPath -Append
  if ($LASTEXITCODE -eq 3) {
    throw "Obs shape mismatch detected in precheck. Retrain model/VecNormalize before eval."
  }
}

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath no existe: $RepoPath"
}

$reportRoot = Join-Path $RepoPath "assault_sim\session\reports\sb3_eval"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = if ([string]::IsNullOrWhiteSpace($OutDir)) {
  Join-Path $reportRoot "run_$stamp"
} else {
  $OutDir
}
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$logFile = Join-Path $runDir "pipeline.log"
$heartbeatFile = Join-Path $runDir "heartbeat.txt"

$summary = [System.Collections.Generic.List[string]]::new()
$summary.Add("run_dir=$runDir")
$summary.Add("repo=$RepoPath")
$summary.Add("episodes=$Episodes")
$summary.Add("seeds=$($Seeds -join ',')")
$summary.Add("skip_train=$([bool]$SkipTrain)")
$summary.Add("parallel_eval=$([bool]$ParallelEvalSeeds)")
$summary.Add("parallel_eval_jobs=$EvalParallelJobs")
  $summary.Add("auto_gate=$([bool]$AutoGateAndPromoteBaseline)")
$summary.Add("auto_compare_gate=$([bool]$AutoCompareAgainstBaseline)")
$summary.Add("fail_on_compare_nogo=$([bool]$FailOnCompareNoGo)")

Push-Location $RepoPath
try {
  # Activar venv si existe.
  $activatePath = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"
  if (Test-Path $activatePath) {
    . $activatePath
    Write-Log "Venv activado: $activatePath" $logFile
  } else {
    Write-Log "Venv no encontrado; se usará python del PATH." $logFile
  }

  if (-not $SkipTrain) {
    Run-Step -Title "TRAIN" -Command @("python", "-m", "assault_sim.train.train_sb3") -FilePath $logFile -HeartbeatPath $heartbeatFile
  } else {
    Write-Log "TRAIN omitido por -SkipTrain." $logFile
    Set-Content -Path $heartbeatFile -Value ("status=running`nstep=EVAL`nstarted_at={0}`nlast_update={0}`nelapsed_seconds=0" -f (Get-Date).ToString("s"))
  }

  Test-ObsShapeCompatibility -RepoRoot $RepoPath -LogPath $logFile

  if ($ParallelEvalSeeds -and $Seeds.Count -gt 1) {
    if ($EvalParallelJobs -lt 1) {
      throw "EvalParallelJobs must be >= 1"
    }
    Write-Log "==== EVAL (parallel seeds) ====" $logFile
    $seedOutRoot = Join-Path $runDir "parallel_eval_seeds"
    New-Item -ItemType Directory -Force -Path $seedOutRoot | Out-Null
    $jobs = @()
    foreach ($seed in $Seeds) {
      while (@($jobs | Where-Object { $_.State -eq "Running" }).Count -ge $EvalParallelJobs) {
        Start-Sleep -Seconds 2
      }
      $seedOut = Join-Path $seedOutRoot ("seed_{0}" -f $seed)
      New-Item -ItemType Directory -Force -Path $seedOut | Out-Null
      Write-Log ("Spawn eval seed {0} -> {1}" -f $seed, $seedOut) $logFile
      $jobs += Start-Job -Name ("eval_seed_{0}" -f $seed) -ScriptBlock {
        param($repo, $seedArg, $episodesArg, $outArg)
        Set-Location $repo
        & python -m assault_sim.evaluation.eval_sb3 --seed $seedArg --episodes $episodesArg --out-dir $outArg 2>&1
        [pscustomobject]@{
          seed = $seedArg
          out_dir = $outArg
          exit_code = $LASTEXITCODE
        }
      } -ArgumentList $RepoPath, $seed, $Episodes, $seedOut
    }
    foreach ($job in $jobs) {
      $jobOutput = Receive-Job -Job $job -Wait
      $lastLine = $null
      if ($jobOutput) {
        $jobOutput | ForEach-Object {
          $line = [string]$_
          if (-not [string]::IsNullOrWhiteSpace($line)) { $lastLine = $line }
        }
      }
      if (-not [string]::IsNullOrWhiteSpace($lastLine)) {
        Write-Log ("[parallel-eval] {0}" -f $lastLine) $logFile
      }
      $state = $job.ChildJobs[0].JobStateInfo.State
      $meta = @($jobOutput | Where-Object { $_ -is [pscustomobject] -and $_.PSObject.Properties.Name -contains "seed" } | Select-Object -Last 1)
      if ($state -ne "Completed" -or $meta.Count -eq 0 -or [int]$meta[0].exit_code -ne 0) {
        $seedName = if ($meta.Count -gt 0) { $meta[0].seed } else { $job.Name }
        $summary.Add("seed_$seedName=failed")
        Write-Log ("ERROR en EVAL seed {0}: state={1}" -f $seedName, $state) $logFile
        if (-not $ContinueOnEvalError) {
          throw "Parallel EVAL failed for seed $seedName"
        }
      } else {
        $summary.Add("seed_$($meta[0].seed)=ok")
      }
      Remove-Job -Job $job -Force -ErrorAction SilentlyContinue | Out-Null
    }
  } else {
    foreach ($seed in $Seeds) {
      $title = "EVAL seed $seed"
      $cmd = @(
        "python", "-m", "assault_sim.evaluation.eval_sb3",
        "--seed", "$seed",
        "--episodes", "$Episodes",
        "--out-dir", "$runDir"
      )

      try {
        Run-Step -Title $title -Command $cmd -FilePath $logFile -HeartbeatPath $heartbeatFile
        $summary.Add("seed_$seed=ok")
      } catch {
        $summary.Add("seed_$seed=failed")
        Write-Log ("ERROR en {0}: {1}" -f $title, $_.Exception.Message) $logFile
        if (-not $ContinueOnEvalError) {
          throw
        }
      }
    }
  }

  $reportFiles = @(
    Get-ChildItem -Path $runDir -Filter "metrics_sb3_report_*.json" -Recurse -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending
  )
  if ($reportFiles) {
    Write-Log "Reportes JSON generados:" $logFile
    foreach ($f in $reportFiles) {
      Write-Log " - $($f.FullName)" $logFile
    }
  } else {
    Write-Log "No se detectaron reportes JSON en $runDir." $logFile
  }

  if ($AutoGateAndPromoteBaseline) {
    if ($reportFiles.Count -lt 1) {
      throw "Auto gate requested but no report JSON was generated in $runDir."
    }
    $latestReport = $reportFiles[0].FullName
    $metrics = Get-GateMetricsFromReport -ReportPath $latestReport
    $gate = Evaluate-Gate `
      -Metrics $metrics `
      -TrueWinMin $GateTrueWinRateMin `
      -LossMax $GateLossRateMax `
      -StrategyStuckMax $GateStrategyStuckMax `
      -VpEntryMissedMax $GateVpEntryMissedMax `
      -PositionReversalMax $GatePositionReversalMax `
      -Captured45Min $GateCaptured45MinEpisodes

    $decision = if ($gate.passed_all) { "GO" } else { "NO-GO" }
    $decisionPayload = [ordered]@{
      run_dir = $runDir
      report_path = $latestReport
      decision = $decision
      gate_thresholds = [ordered]@{
        true_win_rate_min = $GateTrueWinRateMin
        loss_rate_max = $GateLossRateMax
        strategy_stuck_max = $GateStrategyStuckMax
        vp_entry_missed_max_strict = $GateVpEntryMissedMax
        position_reversal_max = $GatePositionReversalMax
        captured_4_5_min_episodes = $GateCaptured45MinEpisodes
      }
      metrics = $metrics
      checks = $gate.checks
      failed_checks = $gate.failed_checks
      promoted_baseline_dir = $null
      decided_at_utc = (Get-Date).ToUniversalTime().ToString("s") + "Z"
    }

    if ($gate.passed_all) {
      $promoted = Promote-BaselineArtifacts `
        -RepoRoot $RepoPath `
        -RunDir $runDir `
        -ReportPath $latestReport `
        -RlSide $metrics.rl_side `
        -BaselineRoot $BaselineRootDir
      $decisionPayload.promoted_baseline_dir = $promoted
      Write-Log "AUTO-GATE: GO -> baseline promoted to $promoted" $logFile
      $summary.Add("gate=GO")
    } else {
      Write-Log ("AUTO-GATE: NO-GO -> failed checks: " + ($gate.failed_checks -join ", ")) $logFile
      $summary.Add("gate=NO-GO")
    }
    $decisionPath = Join-Path $runDir "gate_decision.json"
    ($decisionPayload | ConvertTo-Json -Depth 8) | Set-Content -Path $decisionPath
    Write-Log "Gate decision saved: $decisionPath" $logFile
  }

  if ($AutoCompareAgainstBaseline) {
    if ($reportFiles.Count -lt 1) {
      throw "Auto compare gate requested but no report JSON was generated in $runDir."
    }
    $resolvedBaselineReportPath = Resolve-BaselineReportPath -RepoRoot $RepoPath -ExplicitPath $CompareBaselineReportPath
    $latestReport = $reportFiles[0].FullName
    $goodMetrics = Get-GateMetricsFromReport -ReportPath $resolvedBaselineReportPath
    $badMetrics = Get-GateMetricsFromReport -ReportPath $latestReport
    $compareGate = Evaluate-CompareGate `
      -GoodMetrics $goodMetrics `
      -BadMetrics $badMetrics `
      -TrueWinRateDeltaMin $CompareTrueWinRateDeltaMin `
      -Captured45DeltaMin $CompareCaptured45DeltaMin `
      -VpEntryMissedDeltaMax $CompareVpEntryMissedDeltaMax

    $compareDecision = if ($compareGate.passed_all) { "GO" } else { "NO-GO" }
    $comparePayload = [ordered]@{
      run_dir = $runDir
      baseline_report_path = $resolvedBaselineReportPath
      candidate_report_path = $latestReport
      decision = $compareDecision
      thresholds = [ordered]@{
        true_win_rate_delta_min = $CompareTrueWinRateDeltaMin
        captured_4_5_delta_min = $CompareCaptured45DeltaMin
        vp_entry_missed_rate_delta_max = $CompareVpEntryMissedDeltaMax
      }
      baseline_metrics = $goodMetrics
      candidate_metrics = $badMetrics
      deltas = $compareGate.deltas
      checks = $compareGate.checks
      failed_checks = $compareGate.failed_checks
      decided_at_utc = (Get-Date).ToUniversalTime().ToString("s") + "Z"
    }
    $comparePath = Join-Path $runDir "compare_gate_decision.json"
    ($comparePayload | ConvertTo-Json -Depth 8) | Set-Content -Path $comparePath
    if ($compareGate.passed_all) {
      Write-Log "AUTO-COMPARE-GATE: GO" $logFile
      $summary.Add("compare_gate=GO")
    } else {
      Write-Log ("AUTO-COMPARE-GATE: NO-GO -> failed checks: " + ($compareGate.failed_checks -join ", ")) $logFile
      $summary.Add("compare_gate=NO-GO")
      if ($FailOnCompareNoGo) {
        throw ("AUTO-COMPARE-GATE failed with NO-GO and FailOnCompareNoGo is enabled. Failed checks: " + ($compareGate.failed_checks -join ", "))
      }
    }
    Write-Log "AUTO-COMPARE-GATE baseline report: $resolvedBaselineReportPath" $logFile
    Write-Log "Compare gate decision saved: $comparePath" $logFile
  }

  Write-Log "OK. Resultados en: $runDir" $logFile
  $finishedAt = Get-Date
  Set-Content -Path $heartbeatFile -Value ("status=finished`nstep=ALL`nstarted_at={0}`nlast_update={1}`nelapsed_seconds=0" -f $stamp, $finishedAt.ToString("s"))
  Write-Host "OK. Resultados en: $runDir"
}
finally {
  Pop-Location
  Write-Host "Resumen: $($summary -join ' | ')"
}