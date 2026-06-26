[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [string[]]$Configs = @(
    "C:\repos\python\assault\assault_sim\session\tmp_parallel\train_config_battaglia_cittadina_2_1_us.parallel.json",
    "C:\repos\python\assault\assault_sim\session\tmp_parallel\train_config_battaglia_cittadina_2_1_it.parallel.json",
    "C:\repos\python\assault\assault_sim\session\tmp_parallel\train_config_mettete_i_piedi_terra_1_us.parallel.json",
    "C:\repos\python\assault\assault_sim\session\tmp_parallel\train_config_mettete_i_piedi_terra_1_ge.parallel.json"
  ),
  [int]$Episodes = 20,
  [int]$Seed = 42,
  [int]$MaxParallel = 4,
  [string]$OutRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SafeName {
  param([string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) { return "unnamed" }
  return -join ($Value.ToCharArray() | ForEach-Object {
    if ([char]::IsLetterOrDigit($_) -or $_ -in @('-', '_', '.')) { $_ } else { '_' }
  })
}

function Get-LatestEvalReport {
  param([string]$DirPath)
  if (-not (Test-Path -Path $DirPath -PathType Container)) { return $null }
  $reports = @(Get-ChildItem -Path $DirPath -Filter "metrics_sb3_report_*.json" -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending)
  if ($reports.Count -lt 1) { return $null }
  return $reports[0].FullName
}

function Convert-CountsToString {
  param($CountsObject)
  if ($null -eq $CountsObject) { return "" }
  $parts = @()
  foreach ($p in $CountsObject.PSObject.Properties) {
    $parts += ("{0}:{1}" -f [string]$p.Name, [string]$p.Value)
  }
  if ($parts.Count -lt 1) { return "" }
  return ($parts -join ", ")
}

function Get-CapturedToResultMapping {
  param(
    [string]$RepoRoot,
    [string]$ScenarioId
  )
  try {
    $scenarioPath = Join-Path $RepoRoot ("assault_sim\assets\scenarios\{0}.json" -f $ScenarioId)
    if (-not (Test-Path -Path $scenarioPath -PathType Leaf)) { return "" }
    $scenario = Get-Content -Path $scenarioPath -Raw | ConvertFrom-Json
    $table = @($scenario.victory_outcomes.table)
    if ($table.Count -lt 1) { return "" }
    $parts = @()
    foreach ($row in $table) {
      $min = $row.captured.min
      $max = $row.captured.max
      $result = [string]$row.result
      $parts += ("{0}-{1}:{2}" -f $min, $max, $result)
    }
    return ($parts -join " | ")
  }
  catch {
    return ""
  }
}

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath does not exist: $RepoPath"
}
if ($MaxParallel -lt 1) {
  throw "MaxParallel must be >= 1"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ([string]::IsNullOrWhiteSpace($OutRoot)) {
  $OutRoot = Join-Path $RepoPath ("assault_sim\session\reports\sb3_eval\parallel_configs_{0}" -f $timestamp)
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

Write-Host ("OutRoot: {0}" -f $OutRoot)
Write-Host ("Running {0} evals in parallel (max {1})..." -f $Configs.Count, $MaxParallel)

$jobs = @()
foreach ($cfg in $Configs) {
  if (-not (Test-Path -Path $cfg -PathType Leaf)) {
    Write-Warning ("Config not found; skipping: {0}" -f $cfg)
    continue
  }
  while (@($jobs | Where-Object { $_.State -eq "Running" }).Count -ge $MaxParallel) {
    Start-Sleep -Seconds 2
  }

  $cfgName = Get-SafeName ([System.IO.Path]::GetFileNameWithoutExtension($cfg))
  $jobOutDir = Join-Path $OutRoot $cfgName
  New-Item -ItemType Directory -Path $jobOutDir -Force | Out-Null

  $job = Start-Job -Name ("eval_{0}" -f $cfgName) -ScriptBlock {
    param($repo, $cfgPath, $episodesArg, $seedArg, $outDirArg)
    Set-Location $repo
    & ".\.venv\Scripts\python.exe" -m assault_sim.evaluation.eval_sb3 --config $cfgPath --episodes $episodesArg --seed $seedArg --out-dir $outDirArg 2>&1
    [pscustomobject]@{
      config = $cfgPath
      out_dir = $outDirArg
      exit_code = $LASTEXITCODE
    }
  } -ArgumentList $RepoPath, $cfg, $Episodes, $Seed, $jobOutDir

  $jobs += $job
  Write-Host ("Started {0} -> {1}" -f $job.Name, $jobOutDir)
}

if ($jobs.Count -lt 1) {
  throw "No jobs were started."
}

Write-Host "Waiting jobs..."
$null = $jobs | Wait-Job

$rows = New-Object System.Collections.Generic.List[object]
foreach ($job in $jobs) {
  $output = Receive-Job -Job $job
  $meta = @($output | Where-Object { $_ -is [pscustomobject] -and $_.PSObject.Properties.Name -contains "exit_code" } | Select-Object -Last 1)
  if ($meta.Count -lt 1) {
    Write-Warning ("Job {0}: no metadata found." -f $job.Name)
    continue
  }
  $exitCode = [int]$meta[0].exit_code
  $cfgPath = [string]$meta[0].config
  $jobOutDir = [string]$meta[0].out_dir
  if ($exitCode -ne 0) {
    Write-Warning ("Job {0} failed (exit={1}) config={2}" -f $job.Name, $exitCode, $cfgPath)
    continue
  }

  $reportPath = Get-LatestEvalReport -DirPath $jobOutDir
  if (-not $reportPath) {
    Write-Warning ("Job {0} has no report JSON in {1}" -f $job.Name, $jobOutDir)
    continue
  }

  $report = Get-Content -Path $reportPath -Raw | ConvertFrom-Json
  $comparison = @($report.comparison)
  if ($comparison.Count -lt 1) {
    Write-Warning ("No comparison rows in report: {0}" -f $reportPath)
    continue
  }

  foreach ($r in $comparison) {
    $summaryNode = $null
    $missionNode = $null
    try {
      $summaryNode = $report.by_side_and_scenario.$($r.rl_side).$($r.scenario).summary
      $missionNode = $report.by_side_and_scenario.$($r.rl_side).$($r.scenario).mission
    } catch {
      $summaryNode = $null
      $missionNode = $null
    }
    $capturedFinalCounts = Convert-CountsToString $summaryNode.captured_final_counts
    $trackedResultCounts = Convert-CountsToString $summaryNode.tracked_result_counts
    $capturedToResult = Get-CapturedToResultMapping -RepoRoot $RepoPath -ScenarioId ([string]$r.scenario
    )
    $rows.Add([pscustomobject]@{
      config = [System.IO.Path]::GetFileName($cfgPath)
      side = [string]$r.rl_side
      scenario = [string]$r.scenario
      true_win_rate_objective = [double]$r.true_win_rate
      draw_rate = [double]$r.draw_rate
      loss_rate = [double]$r.loss_rate
      avg_vp = [double]$r.avg_vp
      avg_steps = [double]$r.avg_steps
      trade_mean = [double]$r.trade_mean
      damage_ratio = [double]$r.damage_ratio
      plan_progress_rate = [double]($missionNode.plan_progress_rate -as [double])
      coordination_gain = [double]($missionNode.coordination_gain -as [double])
      avg_legal_actions_per_decision = [double]($missionNode.avg_legal_actions_per_decision -as [double])
      mean_action_catalog_gen_ms = [double]($missionNode.mean_action_catalog_gen_ms -as [double])
      captured_final_counts = $capturedFinalCounts
      tracked_result_counts = $trackedResultCounts
      captured_to_result = $capturedToResult
      report = $reportPath
    }) | Out-Null
  }
}

$jobs | Remove-Job -Force -ErrorAction SilentlyContinue | Out-Null

if ($rows.Count -lt 1) {
  throw "No comparative rows were collected."
}

$sorted = $rows | Sort-Object scenario, side
Write-Host ""
Write-Host "Comparative summary (objective criterion):"
$sorted | Format-Table scenario, side, true_win_rate_objective, draw_rate, loss_rate, avg_vp, avg_steps, trade_mean, damage_ratio -AutoSize

Write-Host ""
Write-Host "VP conversion detail (objective criterion):"
$sorted | Format-Table scenario, side, true_win_rate_objective, captured_final_counts, tracked_result_counts -AutoSize

Write-Host ""
Write-Host "Asymmetry diagnostics (catalog generation):"
$sorted | Format-Table scenario, side, avg_legal_actions_per_decision, mean_action_catalog_gen_ms, plan_progress_rate, coordination_gain -AutoSize

Write-Host ""
Write-Host "Scenario captured->result mapping:"
$sorted |
  Select-Object -Property scenario, captured_to_result -Unique |
  Sort-Object scenario |
  Format-Table -AutoSize

$csvPath = Join-Path $OutRoot "comparative_summary.csv"
$sorted | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host ""
Write-Host ("Saved CSV: {0}" -f $csvPath)
