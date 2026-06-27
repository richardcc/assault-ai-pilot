param(
  [Parameter(Mandatory = $true)][string]$BaselineSnapshot,
  [Parameter(Mandatory = $true)][string]$CandidateSnapshot
)

$ErrorActionPreference = "Stop"

function Get-Snapshot($path) {
  if (-not (Test-Path $path)) { throw "Snapshot not found: $path" }
  return (Get-Content $path -Raw | ConvertFrom-Json)
}

$base = Get-Snapshot $BaselineSnapshot
$cand = Get-Snapshot $CandidateSnapshot

$metrics = @(
  "true_win_rate",
  "loss_rate",
  "vp_entry_conversion_rate",
  "capture_attempt_success_rate",
  "strategy_stuck_ratio",
  "vp_entry_missed_rate",
  "plan_commit_rate",
  "focus_switch_rate",
  "coordination_gain"
)

$rows = @()
foreach ($m in $metrics) {
  $b = [double]($base.mean.$m ?? 0.0)
  $c = [double]($cand.mean.$m ?? 0.0)
  $rows += [PSCustomObject]@{
    metric = $m
    baseline = $b
    candidate = $c
    delta = ($c - $b)
  }
}

$decision = "NO-GO"
$trueWinDelta = ($rows | Where-Object metric -eq "true_win_rate").delta
$lossDelta = ($rows | Where-Object metric -eq "loss_rate").delta
$capDelta = ($rows | Where-Object metric -eq "capture_attempt_success_rate").delta
$stuckDelta = ($rows | Where-Object metric -eq "strategy_stuck_ratio").delta
$missedDelta = ($rows | Where-Object metric -eq "vp_entry_missed_rate").delta

if ($trueWinDelta -ge 0.01 -and $lossDelta -le 0.00 -and $capDelta -ge 0.02 -and $stuckDelta -le 0.00 -and $missedDelta -le 0.00) {
  $decision = "GO"
} elseif ($trueWinDelta -ge 0.00 -and $lossDelta -le 0.03 -and $capDelta -ge 0.00) {
  $decision = "CONDITIONAL GO"
}

Write-Host ("Baseline : {0}" -f $BaselineSnapshot)
Write-Host ("Candidate: {0}" -f $CandidateSnapshot)
Write-Host ""
$rows | Format-Table -AutoSize
Write-Host ""
Write-Host ("A/B Decision: {0}" -f $decision)
