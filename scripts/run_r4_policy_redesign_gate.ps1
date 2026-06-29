param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [int]$Seed = 42,
  [int]$MicroEpisodes = 20,
  [int]$FullEpisodes = 120,
  [double]$TargetStepinSelectionRate = 0.50,
  [double]$KillMinSelectionRate = 0.35,
  [double]$KillMaxVpEntryMissedRate = 0.92
)

$ErrorActionPreference = "Stop"

function Get-LatestReportPath {
  param([string]$ReportsDir)
  if (-not (Test-Path -Path $ReportsDir -PathType Container)) { return $null }
  $latest = Get-ChildItem -Path $ReportsDir -Recurse -File -Filter "metrics_sb3_report_*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latest) { return $null }
  return $latest.FullName
}

function Get-ScenarioMissionMetrics {
  param(
    [string]$ReportPath,
    [string]$Side,
    [string]$Scenario
  )
  $report = (Get-Content $ReportPath -Raw | ConvertFrom-Json)
  $payload = $report.by_side_and_scenario.$Side.$Scenario
  if ($null -eq $payload) {
    throw "No se encontro side/scenario en reporte: side=$Side scenario=$Scenario report=$ReportPath"
  }
  $mission = $payload.mission
  if ($null -eq $mission) {
    throw "No se encontro bloque mission en reporte: $ReportPath"
  }
  $stepin = 0.0
  $missed = 1.0
  try { $stepin = [double]($mission.vp_stepin_selection_rate) } catch { $stepin = 0.0 }
  try { $missed = [double]($mission.vp_entry_missed_rate) } catch { $missed = 1.0 }
  return [pscustomobject]@{
    vp_stepin_selection_rate = $stepin
    vp_entry_missed_rate = $missed
  }
}

function Run-EvalAndReadMetrics {
  param(
    [string]$Repo,
    [string]$ReportsDir,
    [int]$Episodes,
    [int]$Seed,
    [string]$Side,
    [string]$Scenario
  )
  $before = Get-LatestReportPath -ReportsDir $ReportsDir
  python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed $Seed
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "eval_sb3 fallo (episodes=$Episodes seed=$Seed exit=$exitCode)"
  }
  $after = Get-LatestReportPath -ReportsDir $ReportsDir
  if ([string]::IsNullOrWhiteSpace($after)) {
    throw "No se encontro reporte luego de eval_sb3 (episodes=$Episodes seed=$Seed)"
  }
  if ($before -and $before -eq $after) {
    Write-Warning "No cambio ruta de reporte; usando ultimo disponible: $after"
  }
  $metrics = Get-ScenarioMissionMetrics -ReportPath $after -Side $Side -Scenario $Scenario
  return [pscustomobject]@{
    report_path = $after
    episodes = $Episodes
    seed = $Seed
    vp_stepin_selection_rate = [double]$metrics.vp_stepin_selection_rate
    vp_entry_missed_rate = [double]$metrics.vp_entry_missed_rate
  }
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $reportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
  New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null

  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $closeoutJson = Join-Path $reportsDir ("r4_closeout_" + $stamp + ".json")
  $closeoutMd = Join-Path $reportsDir ("r4_closeout_" + $stamp + ".md")

  Write-Host "=== R4 micro-benchmark (20 eps) ===" -ForegroundColor Cyan
  $micro = Run-EvalAndReadMetrics `
    -Repo $Repo `
    -ReportsDir $reportsDir `
    -Episodes $MicroEpisodes `
    -Seed $Seed `
    -Side $Side `
    -Scenario $Scenario

  $microSelection = [double]$micro.vp_stepin_selection_rate
  $microMissed = [double]$micro.vp_entry_missed_rate

  $killTriggered = ($microSelection -lt $KillMinSelectionRate) -or ($microMissed -ge $KillMaxVpEntryMissedRate)
  $microPass = ($microSelection -ge $TargetStepinSelectionRate) -and (-not $killTriggered)

  $full = $null
  $fullPass = $false
  if ($microPass) {
    Write-Host "=== R4 full-benchmark (120 eps) ===" -ForegroundColor Cyan
    $full = Run-EvalAndReadMetrics `
      -Repo $Repo `
      -ReportsDir $reportsDir `
      -Episodes $FullEpisodes `
      -Seed $Seed `
      -Side $Side `
      -Scenario $Scenario
    $fullSelection = [double]$full.vp_stepin_selection_rate
    $fullMissed = [double]$full.vp_entry_missed_rate
    $fullPass = ($fullSelection -ge $TargetStepinSelectionRate) -and ($fullMissed -lt $KillMaxVpEntryMissedRate)
  }

  $decision = "NO-GO"
  if ($microPass -and $fullPass) {
    $decision = "GO"
  } elseif ($microPass -and $null -eq $full) {
    $decision = "CONDITIONAL GO"
  }
  if ($killTriggered) {
    $decision = "KILL"
  }

  $payload = [pscustomobject]@{
    cycle = "R4_POLICY_REDESIGN"
    timestamp_utc = $stamp
    side = $Side
    scenario = $Scenario
    seed = $Seed
    thresholds = [pscustomobject]@{
      target_vp_stepin_selection_rate = $TargetStepinSelectionRate
      kill_min_selection_rate = $KillMinSelectionRate
      kill_max_vp_entry_missed_rate = $KillMaxVpEntryMissedRate
    }
    micro = $micro
    micro_pass = $microPass
    kill_triggered = $killTriggered
    full = $full
    full_pass = $fullPass
    decision = $decision
  }

  $json = $payload | ConvertTo-Json -Depth 20
  [System.IO.File]::WriteAllText($closeoutJson, $json, (New-Object System.Text.UTF8Encoding($false)))

  $md = @(
    "# R4 closeout",
    "",
    "- timestamp_utc: $stamp",
    "- side: $Side",
    "- scenario: $Scenario",
    "- seed: $Seed",
    "- micro_report: $($micro.report_path)",
    "- micro_vp_stepin_selection_rate: $([string]::Format('{0:N4}', $micro.vp_stepin_selection_rate))",
    "- micro_vp_entry_missed_rate: $([string]::Format('{0:N4}', $micro.vp_entry_missed_rate))",
    "- micro_pass: $microPass",
    "- kill_triggered: $killTriggered",
    "- full_report: $($(if ($null -ne $full) { $full.report_path } else { '-' }))",
    "- full_pass: $fullPass",
    "- decision: $decision",
    "",
    "Thresholds:",
    "- target vp_stepin_selection_rate >= $TargetStepinSelectionRate",
    "- kill if selection_rate < $KillMinSelectionRate",
    "- kill if vp_entry_missed_rate >= $KillMaxVpEntryMissedRate"
  ) -join "`n"
  [System.IO.File]::WriteAllText($closeoutMd, $md, (New-Object System.Text.UTF8Encoding($false)))

  Write-Host ""
  Write-Host "R4 decision: $decision" -ForegroundColor Cyan
  Write-Host "Closeout JSON: $closeoutJson"
  Write-Host "Closeout MD:   $closeoutMd"

  if ($decision -eq "GO") {
    exit 0
  }
  exit 1
}
finally {
  Pop-Location
}
