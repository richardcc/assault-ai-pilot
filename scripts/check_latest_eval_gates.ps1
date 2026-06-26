param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$ReportsDir = "",
  [string]$ReportPath = "",
  [string]$Side = "",
  [string]$Scenario = "",
  [string]$CaptureMetric = "capture_conversion_after_contact",
  [double]$MinCaptureAttemptSuccessRate = 0.0000001,
  [double]$MaxLossRate = 0.8,
  [double]$MinVpEntryConversionRate = 0.30
)

$ErrorActionPreference = "Stop"

function Resolve-ReportPath {
  param(
    [string]$RootDir,
    [string]$ExplicitPath
  )

  if ($ExplicitPath) {
    if (-not (Test-Path $ExplicitPath)) {
      throw "ReportPath no existe: $ExplicitPath"
    }
    return (Resolve-Path $ExplicitPath).Path
  }

  if (-not (Test-Path $RootDir)) {
    throw "ReportsDir no existe: $RootDir"
  }

  $latest = Get-ChildItem -Path $RootDir -Recurse -File -Filter "metrics_sb3_report_*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  if ($null -eq $latest) {
    throw "No se encontro ningun metrics_sb3_report_*.json en: $RootDir"
  }
  return $latest.FullName
}

function Resolve-ReportPathForFilters {
  param(
    [string]$RootDir,
    [string]$ExplicitPath,
    [string]$SideFilter,
    [string]$ScenarioFilter
  )

  # If explicit path is provided, keep current strict behavior.
  if ($ExplicitPath) {
    return Resolve-ReportPath -RootDir $RootDir -ExplicitPath $ExplicitPath
  }

  # No filters: keep "latest report" behavior.
  if (-not $SideFilter -and -not $ScenarioFilter) {
    return Resolve-ReportPath -RootDir $RootDir -ExplicitPath $ExplicitPath
  }

  if (-not (Test-Path $RootDir)) {
    throw "ReportsDir no existe: $RootDir"
  }

  $candidates = Get-ChildItem -Path $RootDir -Recurse -File -Filter "metrics_sb3_report_*.json" |
    Sort-Object LastWriteTime -Descending

  foreach ($candidate in $candidates) {
    try {
      $payload = (Get-Content $candidate.FullName -Raw | ConvertFrom-Json)
      if (Report-MatchesFilters -Report $payload -SideFilter $SideFilter -ScenarioFilter $ScenarioFilter) {
        return $candidate.FullName
      }
    } catch {
      # Ignore malformed/non-readable report candidates and keep scanning.
      continue
    }
  }

  throw "No se encontro ningun reporte que cumpla filtros (Side='$SideFilter', Scenario='$ScenarioFilter') en: $RootDir"
}

function Get-MissionRows {
  param(
    $Report,
    [string]$CaptureMetricField
  )

  $rows = @()
  $bySide = $Report.by_side_and_scenario
  if ($null -eq $bySide) {
    return $rows
  }

  foreach ($sideProp in $bySide.PSObject.Properties) {
    $side = [string]$sideProp.Name
    $scenarioMap = $sideProp.Value
    if ($null -eq $scenarioMap) { continue }

    foreach ($scenarioProp in $scenarioMap.PSObject.Properties) {
      $scenario = [string]$scenarioProp.Name
      $payload = $scenarioProp.Value
      if ($null -eq $payload) { continue }

      $summary = $payload.summary
      $mission = $payload.mission
      if ($null -eq $summary -or $null -eq $mission) { continue }

      $episodes = [double]($summary.episodes)
      if ($episodes -le 0) { $episodes = 1.0 }

      $lossRate = [double]($summary.loss_rate)
      $rlCounts = $summary.rl_result_counts
      if ($null -ne $rlCounts) {
        $rlLoss = 0.0
        try { $rlLoss = [double]($rlCounts.loss) } catch { $rlLoss = 0.0 }
        $lossRate = $rlLoss / $episodes
      }

      $captureRate = 0.0
      if ($CaptureMetricField -and $null -ne $mission.$CaptureMetricField) {
        $captureRate = [double]($mission.$CaptureMetricField)
      } elseif ($null -ne $mission.capture_attempt_success_rate) {
        # backward-compat fallback
        $captureRate = [double]($mission.capture_attempt_success_rate)
      }

      $vpConvRate = 0.0
      if ($null -ne $mission.vp_entry_conversion_rate) {
        $vpConvRate = [double]($mission.vp_entry_conversion_rate)
      }

      $rows += [PSCustomObject]@{
        side = $side
        scenario = $scenario
        loss_rate = $lossRate
        capture_attempt_success_rate = $captureRate
        vp_entry_conversion_rate = $vpConvRate
      }
    }
  }

  return $rows
}

function Filter-MissionRows {
  param(
    [array]$Rows,
    [string]$SideFilter,
    [string]$ScenarioFilter
  )

  $filtered = $Rows
  if ($SideFilter) {
    $sideNorm = $SideFilter.Trim().ToUpperInvariant()
    $filtered = $filtered | Where-Object { [string]$_.side -eq $sideNorm }
  }
  if ($ScenarioFilter) {
    $scenarioNorm = $ScenarioFilter.Trim()
    $filtered = $filtered | Where-Object { [string]$_.scenario -eq $scenarioNorm }
  }
  return @($filtered)
}

function Report-MatchesFilters {
  param(
    $Report,
    [string]$SideFilter,
    [string]$ScenarioFilter
  )

  $rowsLocal = Get-MissionRows -Report $Report
  $rowsLocal = Filter-MissionRows -Rows $rowsLocal -SideFilter $SideFilter -ScenarioFilter $ScenarioFilter
  if ($rowsLocal.Count -gt 0) {
    return $true
  }

  $cmp = @($Report.comparison)
  if ($cmp.Count -lt 1) {
    return $false
  }

  $sideNorm = ""
  if ($SideFilter) { $sideNorm = $SideFilter.Trim().ToUpperInvariant() }
  $scenarioNorm = ""
  if ($ScenarioFilter) { $scenarioNorm = $ScenarioFilter.Trim() }

  foreach ($r in $cmp) {
    $rSide = [string]$r.rl_side
    $rScenario = [string]$r.scenario
    if ($sideNorm -and ([string]::IsNullOrWhiteSpace($rSide) -or $rSide.Trim().ToUpperInvariant() -ne $sideNorm)) {
      continue
    }
    if ($scenarioNorm -and ([string]::IsNullOrWhiteSpace($rScenario) -or $rScenario.Trim() -ne $scenarioNorm)) {
      continue
    }
    return $true
  }

  return $false
}

function Test-GateValue {
  param(
    [double]$Value,
    [string]$Op,
    [double]$Threshold
  )

  switch ($Op) {
    "gt" { return $Value -gt $Threshold }
    "ge" { return $Value -ge $Threshold }
    "lt" { return $Value -lt $Threshold }
    "le" { return $Value -le $Threshold }
    default { throw "Operador no soportado: $Op" }
  }
}

if (-not $ReportsDir) {
  $ReportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
}

$resolvedReport = Resolve-ReportPathForFilters `
  -RootDir $ReportsDir `
  -ExplicitPath $ReportPath `
  -SideFilter $Side `
  -ScenarioFilter $Scenario
$report = (Get-Content $resolvedReport -Raw | ConvertFrom-Json)
$rows = Get-MissionRows -Report $report -CaptureMetricField $CaptureMetric
$rows = Filter-MissionRows -Rows $rows -SideFilter $Side -ScenarioFilter $Scenario

if ($rows.Count -eq 0) {
  $cmpRows = @($report.comparison)
  if ($cmpRows.Count -gt 0) {
    $sideNorm = ""
    if ($Side) { $sideNorm = $Side.Trim().ToUpperInvariant() }
    $scenarioNorm = ""
    if ($Scenario) { $scenarioNorm = $Scenario.Trim() }
    foreach ($c in $cmpRows) {
      $cSide = [string]$c.rl_side
      $cScenario = [string]$c.scenario
      if ($sideNorm -and ([string]::IsNullOrWhiteSpace($cSide) -or $cSide.Trim().ToUpperInvariant() -ne $sideNorm)) { continue }
      if ($scenarioNorm -and ([string]::IsNullOrWhiteSpace($cScenario) -or $cScenario.Trim() -ne $scenarioNorm)) { continue }
      $rows += [PSCustomObject]@{
        side = $cSide
        scenario = $cScenario
        loss_rate = [double]($c.loss_rate)
        capture_attempt_success_rate = 0.0
        vp_entry_conversion_rate = 0.0
      }
    }
  }
}

if ($rows.Count -eq 0) {
  throw "No hay filas side/scenario que cumplan los filtros (Side='$Side', Scenario='$Scenario') en: $resolvedReport"
}

Write-Host ""
Write-Host "=== Gate Check (post-run) ==="
Write-Host "Report: $resolvedReport"
if ($Side -or $Scenario) {
  Write-Host ("Filters: side={0}; scenario={1}" -f $(if ($Side) { $Side } else { "*" }), $(if ($Scenario) { $Scenario } else { "*" }))
}
Write-Host ("Thresholds: {0} > {1}; loss_rate < {2}; vp_entry_conversion_rate >= {3}" -f `
  $CaptureMetric, `
  $MinCaptureAttemptSuccessRate, $MaxLossRate, $MinVpEntryConversionRate)
Write-Host ""

$anyFail = $false
$perRow = @()

foreach ($r in $rows) {
  $okCapture = Test-GateValue -Value $r.capture_attempt_success_rate -Op "gt" -Threshold $MinCaptureAttemptSuccessRate
  $okLoss = Test-GateValue -Value $r.loss_rate -Op "lt" -Threshold $MaxLossRate
  $okVpConv = Test-GateValue -Value $r.vp_entry_conversion_rate -Op "ge" -Threshold $MinVpEntryConversionRate
  $rowPass = $okCapture -and $okLoss -and $okVpConv
  if (-not $rowPass) { $anyFail = $true }

  $perRow += [PSCustomObject]@{
    side = $r.side
    scenario = $r.scenario
    capture_metric = $CaptureMetric
    capture_metric_value = [math]::Round($r.capture_attempt_success_rate, 4)
    loss_rate = [math]::Round($r.loss_rate, 4)
    vp_entry_conversion_rate = [math]::Round($r.vp_entry_conversion_rate, 4)
    gate_capture = $(if ($okCapture) { "PASS" } else { "FAIL" })
    gate_loss = $(if ($okLoss) { "PASS" } else { "FAIL" })
    gate_vp_conversion = $(if ($okVpConv) { "PASS" } else { "FAIL" })
    gate_row = $(if ($rowPass) { "PASS" } else { "FAIL" })
  }
}

$perRow | Format-Table -AutoSize

$aggCapture = ($rows | Measure-Object -Property capture_attempt_success_rate -Average).Average
$aggLoss = ($rows | Measure-Object -Property loss_rate -Average).Average
$aggVpConv = ($rows | Measure-Object -Property vp_entry_conversion_rate -Average).Average

$aggCaptureOk = Test-GateValue -Value $aggCapture -Op "gt" -Threshold $MinCaptureAttemptSuccessRate
$aggLossOk = Test-GateValue -Value $aggLoss -Op "lt" -Threshold $MaxLossRate
$aggVpConvOk = Test-GateValue -Value $aggVpConv -Op "ge" -Threshold $MinVpEntryConversionRate
$aggPass = $aggCaptureOk -and $aggLossOk -and $aggVpConvOk

Write-Host ""
Write-Host "=== Aggregate (mean across side/scenario rows) ==="
Write-Host ("{0}={1:N4} [{2}]" -f $CaptureMetric, $aggCapture, $(if ($aggCaptureOk) { "PASS" } else { "FAIL" }))
Write-Host ("loss_rate={0:N4} [{1}]" -f $aggLoss, $(if ($aggLossOk) { "PASS" } else { "FAIL" }))
Write-Host ("vp_entry_conversion_rate={0:N4} [{1}]" -f $aggVpConv, $(if ($aggVpConvOk) { "PASS" } else { "FAIL" }))
Write-Host ("gate_aggregate={0}" -f $(if ($aggPass) { "PASS" } else { "FAIL" }))

Write-Host ""
if ($anyFail -or -not $aggPass) {
  Write-Host "RESULT: FAIL (al menos un gate no cumple)." -ForegroundColor Red
  exit 1
}

Write-Host "RESULT: PASS (todos los gates cumplen)." -ForegroundColor Green
exit 0

