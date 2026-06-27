param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$Episodes = 50,
  [int[]]$Seeds = @(42, 43, 44),
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [string]$Tag = "strict"
)

$ErrorActionPreference = "Stop"
Set-Location $Repo
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

$reportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
$snapshotsDir = Join-Path $reportsDir "snapshots"
New-Item -ItemType Directory -Path $snapshotsDir -Force | Out-Null

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $Repo "strict_eval_multiseed_$ts.log"
$seedRows = @()

foreach ($seed in $Seeds) {
  Write-Host ""
  Write-Host "=== STRICT EVAL seed=$seed episodes=$Episodes ==="
  $before = @(
    Get-ChildItem $reportsDir -Filter "metrics_sb3_report_*.json" |
      Sort-Object LastWriteTime |
      Select-Object -ExpandProperty FullName
  )
  python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed $seed 2>&1 | Tee-Object -FilePath $log -Append
  $after = @(
    Get-ChildItem $reportsDir -Filter "metrics_sb3_report_*.json" |
      Sort-Object LastWriteTime |
      Select-Object -ExpandProperty FullName
  )
  $new = @($after | Where-Object { $_ -notin $before })
  if (-not $new.Count) {
    throw "No new report produced for seed=$seed"
  }
  $reportPath = $new[-1]
  $report = Get-Content $reportPath -Raw | ConvertFrom-Json
  $payload = $report.by_side_and_scenario.$Side.$Scenario
  if (-not $payload) {
    throw "Missing side/scenario payload for side=$Side scenario=$Scenario in report=$reportPath"
  }
  $summary = $payload.summary
  $mission = $payload.mission
  $seedRows += [PSCustomObject]@{
    seed = [int]$seed
    report_path = $reportPath
    true_win_rate = [double]($summary.true_win_rate ?? 0.0)
    loss_rate = [double]($summary.loss_rate ?? 0.0)
    vp_entry_conversion_rate = [double]($mission.vp_entry_conversion_rate ?? 0.0)
    capture_attempt_success_rate = [double]($mission.capture_attempt_success_rate ?? 0.0)
    strategy_stuck_ratio = [double]($mission.strategy_stuck_ratio ?? 0.0)
    vp_entry_missed_rate = [double]($mission.vp_entry_missed_rate ?? 0.0)
    plan_commit_rate = [double]($mission.plan_commit_rate ?? 0.0)
    focus_switch_rate = [double]($mission.focus_switch_rate ?? 0.0)
    coordination_gain = [double]($mission.coordination_gain ?? 0.0)
  }
}

$mean = @{
  true_win_rate = [double](($seedRows | Measure-Object true_win_rate -Average).Average)
  loss_rate = [double](($seedRows | Measure-Object loss_rate -Average).Average)
  vp_entry_conversion_rate = [double](($seedRows | Measure-Object vp_entry_conversion_rate -Average).Average)
  capture_attempt_success_rate = [double](($seedRows | Measure-Object capture_attempt_success_rate -Average).Average)
  strategy_stuck_ratio = [double](($seedRows | Measure-Object strategy_stuck_ratio -Average).Average)
  vp_entry_missed_rate = [double](($seedRows | Measure-Object vp_entry_missed_rate -Average).Average)
  plan_commit_rate = [double](($seedRows | Measure-Object plan_commit_rate -Average).Average)
  focus_switch_rate = [double](($seedRows | Measure-Object focus_switch_rate -Average).Average)
  coordination_gain = [double](($seedRows | Measure-Object coordination_gain -Average).Average)
}

$decision = "NO-GO"
if ($mean.loss_rate -le 0.50 -and $mean.true_win_rate -ge 0.12 -and $mean.capture_attempt_success_rate -ge 0.10) {
  $decision = "GO"
} elseif ($mean.loss_rate -le 0.60 -and $mean.true_win_rate -ge 0.08 -and $mean.capture_attempt_success_rate -ge 0.06) {
  $decision = "CONDITIONAL GO"
}

$snapshot = [PSCustomObject]@{
  tag = $Tag
  timestamp = (Get-Date).ToUniversalTime().ToString("o")
  episodes = [int]$Episodes
  seeds = $Seeds
  side = $Side
  scenario = $Scenario
  reports = $seedRows
  mean = $mean
  decision = $decision
}

$snapPath = Join-Path $snapshotsDir "p4_snapshot_${Tag}_$ts.json"
$snapshot | ConvertTo-Json -Depth 8 | Set-Content -Path $snapPath -Encoding UTF8

Write-Host ""
Write-Host ("mean true_win_rate             : {0:N3}" -f $mean.true_win_rate)
Write-Host ("mean loss_rate                 : {0:N3}" -f $mean.loss_rate)
Write-Host ("mean vp_entry_conversion_rate  : {0:N3}" -f $mean.vp_entry_conversion_rate)
Write-Host ("mean capture_attempt_success   : {0:N3}" -f $mean.capture_attempt_success_rate)
Write-Host ("mean strategy_stuck_ratio      : {0:N3}" -f $mean.strategy_stuck_ratio)
Write-Host ("mean vp_entry_missed_rate      : {0:N3}" -f $mean.vp_entry_missed_rate)
Write-Host ("mean plan_commit_rate          : {0:N3}" -f $mean.plan_commit_rate)
Write-Host ("mean focus_switch_rate         : {0:N3}" -f $mean.focus_switch_rate)
Write-Host ("mean coordination_gain         : {0:N3}" -f $mean.coordination_gain)
Write-Host ("Decision: {0}" -f $decision)
Write-Host ("Snapshot: {0}" -f $snapPath)
Write-Host ("Log: {0}" -f $log)
