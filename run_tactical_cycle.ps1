param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$EvalEpisodes = 50
)

$ErrorActionPreference = "Stop"

Set-Location $Repo
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

Write-Host "== Tactical cycle start =="
Write-Host "Repo: $Repo"
Write-Host "Eval episodes per seed: $EvalEpisodes"
Write-Host ""

# Keep train run clean (no perf/profiling overhead)
Remove-Item Env:ASSAULT_PERF_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:ASSAULT_PERF_EVERY -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONUNBUFFERED -ErrorAction SilentlyContinue

Write-Host "== TRAIN =="
python -m assault_sim.train.train_sb3

Write-Host ""
Write-Host "== EVAL MULTI-SEED (42/43/44) =="
powershell -ExecutionPolicy Bypass -File ".\run_eval_multiseed_smoke.ps1" -Episodes $EvalEpisodes

Write-Host ""
Write-Host "== SUMMARY (latest report) =="
$reportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
$latest = Get-ChildItem $reportsDir -Filter "metrics_sb3_report_*.json" | Sort-Object LastWriteTime | Select-Object -Last 1
if (-not $latest) {
  Write-Host "[ERROR] No eval report found in $reportsDir"
  exit 1
}

$report = Get-Content $latest.FullName -Raw | ConvertFrom-Json
$entries = @()
foreach ($sideProp in $report.by_side_and_scenario.PSObject.Properties) {
  $side = $sideProp.Name
  foreach ($scProp in $sideProp.Value.PSObject.Properties) {
    $scenario = $scProp.Name
    $payload = $scProp.Value
    $summary = $payload.summary
    $mission = $payload.mission
    $entries += [PSCustomObject]@{
      side = $side
      scenario = $scenario
      true_win_rate = [double]($summary.true_win_rate | ForEach-Object { if ($_ -eq $null) { 0 } else { $_ } })
      loss_rate = [double]($summary.loss_rate | ForEach-Object { if ($_ -eq $null) { 0 } else { $_ } })
      score_win_rate = [double]($summary.win_score_rate | ForEach-Object { if ($_ -eq $null) { 0 } else { $_ } })
      vp_entry_conversion_rate = [double]($mission.vp_entry_conversion_rate | ForEach-Object { if ($_ -eq $null) { 0 } else { $_ } })
      capture_conversion_after_contact = [double]($mission.capture_conversion_after_contact | ForEach-Object { if ($_ -eq $null) { 0 } else { $_ } })
      strategy_stuck_ratio = [double]($mission.strategy_stuck_ratio | ForEach-Object { if ($_ -eq $null) { 0 } else { $_ } })
    }
  }
}

if (-not $entries.Count) {
  Write-Host "[ERROR] No side/scenario entries in latest report: $($latest.Name)"
  exit 1
}

$avgTrueWin = ($entries | Measure-Object true_win_rate -Average).Average
$avgLoss = ($entries | Measure-Object loss_rate -Average).Average
$avgScoreWin = ($entries | Measure-Object score_win_rate -Average).Average
$avgVpConv = ($entries | Measure-Object vp_entry_conversion_rate -Average).Average
$avgCapConv = ($entries | Measure-Object capture_conversion_after_contact -Average).Average
$avgStuck = ($entries | Measure-Object strategy_stuck_ratio -Average).Average

Write-Host "Latest report: $($latest.Name)"
Write-Host ("avg score_win_rate: {0:N3}" -f $avgScoreWin)
Write-Host ("avg true_win_rate : {0:N3}" -f $avgTrueWin)
Write-Host ("avg loss_rate     : {0:N3}" -f $avgLoss)
Write-Host ("avg vp_entry_conv : {0:N3}" -f $avgVpConv)
Write-Host ("avg cap_after_ctc : {0:N3}" -f $avgCapConv)
Write-Host ("avg stuck_ratio   : {0:N3}" -f $avgStuck)

$decision = "NO-GO"
if ($avgLoss -le 0.40 -and $avgTrueWin -ge 0.12) {
  $decision = "GO"
} elseif ($avgLoss -le 0.50 -and $avgTrueWin -ge 0.08) {
  $decision = "CONDITIONAL GO"
}

Write-Host ""
Write-Host ("Decision: {0}" -f $decision)
Write-Host "== Tactical cycle end =="
