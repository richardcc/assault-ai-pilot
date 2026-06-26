<#
.SYNOPSIS
Builds markdown and history summary from trainer sweep gate CSV.

.DESCRIPTION
Consumes `trainer_sweep_gate_decision.csv`, picks a recommended config
(GO first, then CONDITIONAL GO, then best NO-GO candidate),
writes `decision_summary.md`, and appends a row to `trainer_sweep_history.csv`.

.PARAMETER GateCsv
Path to `trainer_sweep_gate_decision.csv`.

.PARAMETER OutMarkdown
Optional output path for markdown summary. Defaults to run folder.

.PARAMETER HistoryCsv
Optional path for cumulative history CSV. Defaults to parent reports folder.

.EXAMPLE
.\scripts\build_trainer_sweep_summary.ps1 -GateCsv "...\trainer_sweep_gate_decision.csv"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$GateCsv,
  [string]$OutMarkdown = "",
  [string]$HistoryCsv = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $GateCsv -PathType Leaf)) {
  throw "Gate CSV not found: $GateCsv"
}

$rows = Import-Csv -Path $GateCsv
if ($rows.Count -lt 1) {
  throw "Gate CSV has no rows: $GateCsv"
}

$goRows = @($rows | Where-Object { [string]$_.decision -eq "GO" })
$candidateRows = if ($goRows.Count -gt 0) { $goRows } else { @($rows | Where-Object { [string]$_.decision -eq "CONDITIONAL GO" }) }
if ($candidateRows.Count -lt 1) { $candidateRows = $rows }

$winner = $candidateRows |
  Sort-Object -Property `
    @{ Expression = { [double]$_.true_win_rate_objective }; Descending = $true }, `
    @{ Expression = { [double]$_.loss_rate }; Descending = $false }, `
    @{ Expression = { [double]$_.vp_entry_missed_rate }; Descending = $false }, `
    @{ Expression = { [int]$_.captured_4_5 }; Descending = $true } |
  Select-Object -First 1

$globalDecision = if ($goRows.Count -gt 0) { "GO" } elseif ((@($rows | Where-Object { [string]$_.decision -eq "CONDITIONAL GO" }).Count -gt 0)) { "CONDITIONAL GO" } else { "NO-GO" }
$promotionAllowed = if ($globalDecision -eq "GO") { "yes" } else { "no" }
$rollbackRequired = if ($globalDecision -eq "NO-GO") { "si" } else { "no" }

$runDir = Split-Path -Path $GateCsv -Parent
if ([string]::IsNullOrWhiteSpace($OutMarkdown)) {
  $OutMarkdown = Join-Path $runDir "decision_summary.md"
}
if ([string]::IsNullOrWhiteSpace($HistoryCsv)) {
  $HistoryCsv = Join-Path (Split-Path -Path $runDir -Parent) "trainer_sweep_history.csv"
}

$ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
$lines = @()
$lines += "# Trainer Sweep Decision Summary"
$lines += ""
$lines += "- Timestamp: $ts"
$lines += "- Global decision: **$globalDecision**"
$lines += "- Promotion allowed: **$promotionAllowed**"
$lines += "- Rollback required: **$rollbackRequired**"
$lines += ""
$lines += "## Recommended Config"
$lines += ""
$lines += ("- config: {0}" -f [string]$winner.config)
$lines += ("- side/scenario: {0} / {1}" -f [string]$winner.side, [string]$winner.scenario)
$lines += ("- true_win_rate_objective: {0}" -f [string]$winner.true_win_rate_objective)
$lines += ("- loss_rate: {0}" -f [string]$winner.loss_rate)
$lines += ("- vp_entry_missed_rate: {0}" -f [string]$winner.vp_entry_missed_rate)
$lines += ("- captured_4_5: {0}" -f [string]$winner.captured_4_5)
$lines += ("- decision: {0}" -f [string]$winner.decision)
$lines += ""
$lines += "## Full Gate Table"
$lines += ""
$lines += "| config | side | scenario | true_win_rate_objective | loss_rate | vp_entry_missed_rate | captured_4_5 | decision | rollback_required |"
$lines += "|---|---|---|---:|---:|---:|---:|---|---|"
foreach ($r in $rows) {
  $lines += "| $($r.config) | $($r.side) | $($r.scenario) | $($r.true_win_rate_objective) | $($r.loss_rate) | $($r.vp_entry_missed_rate) | $($r.captured_4_5) | $($r.decision) | $($r.rollback_required) |"
}

[System.IO.File]::WriteAllText($OutMarkdown, ($lines -join "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("Saved summary markdown: {0}" -f $OutMarkdown)

$historyRow = [pscustomobject]@{
  timestamp = $ts
  run_dir = $runDir
  global_decision = $globalDecision
  promotion_allowed = $promotionAllowed
  rollback_required = $rollbackRequired
  winner_config = [string]$winner.config
  winner_true_win_rate_objective = [double]$winner.true_win_rate_objective
  winner_loss_rate = [double]$winner.loss_rate
  winner_vp_entry_missed_rate = [double]$winner.vp_entry_missed_rate
  winner_captured_4_5 = [int]$winner.captured_4_5
}

if (Test-Path -Path $HistoryCsv -PathType Leaf) {
  $historyRow | Export-Csv -Path $HistoryCsv -NoTypeInformation -Encoding UTF8 -Append
} else {
  $historyRow | Export-Csv -Path $HistoryCsv -NoTypeInformation -Encoding UTF8
}
Write-Host ("Updated history CSV: {0}" -f $HistoryCsv)
