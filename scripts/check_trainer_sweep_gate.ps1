<#
.SYNOPSIS
Evaluates trainer sweep comparative CSV and emits GO/NO-GO decisions.

.DESCRIPTION
Reads comparative summary rows, enriches each row with mission `vp_entry_missed_rate`
from referenced report JSON, applies roadmap gates, and writes `trainer_sweep_gate_decision.csv`.
Returns exit code 1 when no row is GO.

.PARAMETER ComparativeCsv
Path to `comparative_summary.csv` produced by `run_eval_parallel_configs.ps1`.

.PARAMETER MinTrueWinRateObjective
Minimum objective win-rate threshold for PASS.

.PARAMETER MaxLossRate
Maximum allowed loss-rate threshold for PASS.

.PARAMETER MaxVpEntryMissedRate
Maximum allowed VP-entry missed rate threshold for PASS.

.PARAMETER MinCaptured45
Minimum required combined count of captured=4 and captured=5.

.EXAMPLE
.\scripts\check_trainer_sweep_gate.ps1 -ComparativeCsv "...\comparative_summary.csv"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$ComparativeCsv,
  [double]$MinTrueWinRateObjective = 0.10,
  [double]$MaxLossRate = 0.60,
  [double]$MaxVpEntryMissedRate = 1.00,
  [int]$MinCaptured45 = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $ComparativeCsv -PathType Leaf)) {
  throw "Comparative CSV not found: $ComparativeCsv"
}

function Get-CountFromMapString {
  param(
    [string]$MapText,
    [string]$Key
  )
  if ([string]::IsNullOrWhiteSpace($MapText)) { return 0 }
  $parts = $MapText -split ","
  foreach ($p in $parts) {
    $trim = [string]$p
    if ($trim -match "^\s*$([regex]::Escape($Key))\s*:\s*([0-9]+)\s*$") {
      return [int]$matches[1]
    }
  }
  return 0
}

function Get-MissionMetricFromReport {
  param(
    [string]$ReportPath,
    [string]$Side,
    [string]$Scenario,
    [string]$MetricName
  )
  if ([string]::IsNullOrWhiteSpace($ReportPath) -or -not (Test-Path -Path $ReportPath -PathType Leaf)) {
    return $null
  }
  try {
    $r = Get-Content -Path $ReportPath -Raw | ConvertFrom-Json
    $mission = $r.by_side_and_scenario.$Side.$Scenario.mission
    if ($null -eq $mission) { return $null }
    $val = $mission.$MetricName
    if ($null -eq $val) { return $null }
    return [double]$val
  } catch {
    return $null
  }
}

$rows = Import-Csv -Path $ComparativeCsv
if ($rows.Count -lt 1) {
  throw "No rows found in comparative CSV: $ComparativeCsv"
}

$evaluated = New-Object System.Collections.Generic.List[object]

foreach ($r in $rows) {
  $config = [string]$r.config
  $side = [string]$r.side
  $scenario = [string]$r.scenario
  $reportPath = [string]$r.report
  $trueWinObj = [double]$r.true_win_rate_objective
  $lossRate = [double]$r.loss_rate
  $capturedMap = [string]$r.captured_final_counts
  $captured4 = Get-CountFromMapString -MapText $capturedMap -Key "4"
  $captured5 = Get-CountFromMapString -MapText $capturedMap -Key "5"
  $captured45 = $captured4 + $captured5
  $vpMissed = Get-MissionMetricFromReport -ReportPath $reportPath -Side $side -Scenario $scenario -MetricName "vp_entry_missed_rate"
  if ($null -eq $vpMissed) { $vpMissed = 1.0 }

  $okWin = $trueWinObj -ge $MinTrueWinRateObjective
  $okLoss = $lossRate -le $MaxLossRate
  $okMissed = $vpMissed -lt $MaxVpEntryMissedRate
  $okCaptured = $captured45 -ge $MinCaptured45

  $decision = if ($okWin -and $okLoss -and $okMissed -and $okCaptured) { "GO" } elseif ($okWin -and $okLoss) { "CONDITIONAL GO" } else { "NO-GO" }
  $rollback = if ($decision -eq "NO-GO") { "si" } else { "no" }

  $evaluated.Add([pscustomobject]@{
    config = $config
    side = $side
    scenario = $scenario
    true_win_rate_objective = [math]::Round($trueWinObj, 4)
    loss_rate = [math]::Round($lossRate, 4)
    vp_entry_missed_rate = [math]::Round([double]$vpMissed, 4)
    captured_4_5 = $captured45
    gate_win = if ($okWin) { "PASS" } else { "FAIL" }
    gate_loss = if ($okLoss) { "PASS" } else { "FAIL" }
    gate_vp_missed = if ($okMissed) { "PASS" } else { "FAIL" }
    gate_captured_45 = if ($okCaptured) { "PASS" } else { "FAIL" }
    decision = $decision
    rollback_required = $rollback
  }) | Out-Null
}

Write-Host ""
Write-Host "=== Trainer Sweep Gate Decision ==="
$evaluated | Sort-Object config, scenario, side | Format-Table -AutoSize

$outCsv = Join-Path (Split-Path -Path $ComparativeCsv -Parent) "trainer_sweep_gate_decision.csv"
$evaluated | Export-Csv -Path $outCsv -NoTypeInformation -Encoding UTF8
Write-Host ""
Write-Host ("Saved gate decision CSV: {0}" -f $outCsv)

if (($evaluated | Where-Object { $_.decision -eq "GO" }).Count -lt 1) {
  exit 1
}
exit 0
