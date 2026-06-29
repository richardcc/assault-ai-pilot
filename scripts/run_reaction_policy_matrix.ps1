[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int]$Episodes = 50,
  [int]$Seed = 42,
  [string]$OutRoot = "",
  [switch]$EnforceGate,
  [int]$MinAlwaysReactionFireCount = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LatestEvalReport {
  param([string]$DirPath)
  if (-not (Test-Path -Path $DirPath -PathType Container)) { return $null }
  $reports = @(Get-ChildItem -Path $DirPath -Filter "metrics_sb3_report_*.json" -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending)
  if ($reports.Count -lt 1) { return $null }
  return $reports[0].FullName
}

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath does not exist: $RepoPath"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ([string]::IsNullOrWhiteSpace($OutRoot)) {
  $OutRoot = Join-Path $RepoPath ("assault_sim\session\reports\sb3_eval\reaction_policy_matrix_{0}" -f $timestamp)
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$python = Join-Path $RepoPath ".venv\Scripts\python.exe"
if (-not (Test-Path -Path $python -PathType Leaf)) {
  throw "Python venv not found: $python"
}

$policies = @("always", "balanced", "never")
$rows = New-Object System.Collections.Generic.List[object]

Push-Location $RepoPath
try {
  foreach ($policy in $policies) {
    $runOutDir = Join-Path $OutRoot $policy
    New-Item -ItemType Directory -Path $runOutDir -Force | Out-Null

    Write-Host ""
    Write-Host ("=== Running policy={0} episodes={1} seed={2} ===" -f $policy, $Episodes, $Seed)

    $env:ASSAULT_AI_REACTION_POLICY = $policy
    & $python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed $Seed --out-dir $runOutDir
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
      throw ("Eval failed for policy={0} (exit={1})" -f $policy, $exitCode)
    }

    $reportPath = Get-LatestEvalReport -DirPath $runOutDir
    if (-not $reportPath) {
      throw ("No report found for policy={0} in {1}" -f $policy, $runOutDir)
    }

    $report = Get-Content -Path $reportPath -Raw | ConvertFrom-Json
    $comparison = @($report.comparison)
    if ($comparison.Count -lt 1) {
      throw ("No comparison rows in report for policy={0}: {1}" -f $policy, $reportPath)
    }

    foreach ($c in $comparison) {
      $side = [string]$c.rl_side
      $scenario = [string]$c.scenario
      $summary = $report.by_side_and_scenario.$side.$scenario.summary
      $mission = $report.by_side_and_scenario.$side.$scenario.mission
      $scoreWinRate = $null
      if ($null -ne $c.PSObject.Properties["win_score_rate"]) {
        $scoreWinRate = $c.win_score_rate
      } elseif ($null -ne $summary -and $null -ne $summary.PSObject.Properties["win_score_rate"]) {
        $scoreWinRate = $summary.win_score_rate
      } else {
        $scoreWinRate = 0.0
      }

      $rows.Add([pscustomobject]@{
        policy = $policy
        side = $side
        scenario = $scenario
        episodes = $Episodes
        reaction_window_count = [int]($mission.reaction_window_count -as [int])
        reaction_fire_skipped_count = [int]($mission.reaction_fire_skipped_count -as [int])
        reaction_fire_count = [int]($mission.reaction_fire_count -as [int])
        reaction_fire_rate = [double]($mission.reaction_fire_rate -as [double])
        win_score_rate = [double]($scoreWinRate -as [double])
        true_win_rate = [double]($c.true_win_rate -as [double])
        avg_vp = [double]($c.avg_vp -as [double])
        report = $reportPath
      }) | Out-Null
    }
  }
}
finally {
  Remove-Item Env:ASSAULT_AI_REACTION_POLICY -ErrorAction SilentlyContinue
  Pop-Location
}

if ($rows.Count -lt 1) {
  throw "No rows collected."
}

$sorted = $rows | Sort-Object scenario, side, policy

Write-Host ""
Write-Host "=== Reaction policy comparison ==="
$sorted | Format-Table policy, side, scenario, reaction_window_count, reaction_fire_skipped_count, reaction_fire_count, reaction_fire_rate, win_score_rate, true_win_rate, avg_vp -AutoSize

$csvPath = Join-Path $OutRoot "reaction_policy_matrix.csv"
$sorted | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host ("Saved matrix folder: {0}" -f $OutRoot)
Write-Host ("Saved CSV: {0}" -f $csvPath)

if ($EnforceGate) {
  Write-Host ""
  Write-Host "=== Gate checks (Reaction Fire) ==="
  $gateFailures = New-Object System.Collections.Generic.List[string]

  foreach ($row in $sorted) {
    $label = ("policy={0} side={1} scenario={2}" -f $row.policy, $row.side, $row.scenario)
    switch ($row.policy) {
      "always" {
        if ([int]$row.reaction_fire_count -lt $MinAlwaysReactionFireCount) {
          $gateFailures.Add(("{0} -> expected reaction_fire_count >= {1}, got {2}" -f $label, $MinAlwaysReactionFireCount, [int]$row.reaction_fire_count)) | Out-Null
        }
      }
      "never" {
        if ([int]$row.reaction_fire_count -ne 0) {
          $gateFailures.Add(("{0} -> expected reaction_fire_count = 0, got {1}" -f $label, [int]$row.reaction_fire_count)) | Out-Null
        }
      }
      "balanced" {
        if ([int]$row.reaction_fire_count -le 0) {
          $gateFailures.Add(("{0} -> expected reaction_fire_count > 0, got {1}" -f $label, [int]$row.reaction_fire_count)) | Out-Null
        }
        if ([int]$row.reaction_fire_skipped_count -le 0) {
          $gateFailures.Add(("{0} -> expected reaction_fire_skipped_count > 0, got {1}" -f $label, [int]$row.reaction_fire_skipped_count)) | Out-Null
        }
      }
    }
  }

  if ($gateFailures.Count -gt 0) {
    Write-Host "GATE: FAIL"
    foreach ($f in $gateFailures) {
      Write-Host (" - {0}" -f $f)
    }
    throw "Reaction policy gate failed."
  }

  Write-Host "GATE: PASS"
}

