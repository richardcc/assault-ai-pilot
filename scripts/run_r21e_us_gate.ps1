param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(42, 43, 44),
  [int]$Episodes = 10,
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [string]$CaptureMetric = "capture_conversion_after_contact",
  [ValidateSet("strict", "majority", "mean")]
  [string]$PassPolicy = "majority",
  [double]$MinCaptureAttemptSuccessRate = 0.0000001,
  [double]$MaxLossRate = 0.8,
  [double]$MinVpEntryConversionRate = 0.30
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

function Get-ReportGateMetrics {
  param(
    [string]$ReportPath,
    [string]$Side,
    [string]$Scenario,
    [string]$CaptureMetric
  )
  $report = (Get-Content $ReportPath -Raw | ConvertFrom-Json)
  $bySide = $report.by_side_and_scenario
  if ($null -eq $bySide) {
    return $null
  }
  $sideNode = $bySide.$Side
  if ($null -eq $sideNode) {
    return $null
  }
  $payload = $sideNode.$Scenario
  if ($null -eq $payload) {
    return $null
  }
  $summary = $payload.summary
  $mission = $payload.mission
  if ($null -eq $summary -or $null -eq $mission) {
    return $null
  }
  $episodes = 1.0
  try {
    $episodes = [double]($summary.episodes)
    if ($episodes -le 0) { $episodes = 1.0 }
  } catch {
    $episodes = 1.0
  }
  $lossRate = 0.0
  try {
    $lossRate = [double]($summary.loss_rate)
  } catch {
    $lossRate = 0.0
  }
  try {
    if ($null -ne $summary.rl_result_counts -and $null -ne $summary.rl_result_counts.loss) {
      $lossRate = [double]($summary.rl_result_counts.loss) / $episodes
    }
  } catch {}

  $captureValue = 0.0
  try {
    if ($CaptureMetric -and $null -ne $mission.$CaptureMetric) {
      $captureValue = [double]($mission.$CaptureMetric)
    } elseif ($null -ne $mission.capture_attempt_success_rate) {
      $captureValue = [double]($mission.capture_attempt_success_rate)
    }
  } catch {
    $captureValue = 0.0
  }

  $vpConv = 0.0
  try {
    if ($null -ne $mission.vp_entry_conversion_rate) {
      $vpConv = [double]($mission.vp_entry_conversion_rate)
    }
  } catch {
    $vpConv = 0.0
  }

  return [pscustomobject]@{
    capture_metric_value = $captureValue
    loss_rate = $lossRate
    vp_entry_conversion_rate = $vpConv
  }
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $reportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
  $gateScript = Join-Path $Repo "scripts\check_latest_eval_gates.ps1"
  if (-not (Test-Path -Path $gateScript -PathType Leaf)) {
    throw "No existe script de gate: $gateScript"
  }

  $results = New-Object System.Collections.Generic.List[object]
  $metricRows = New-Object System.Collections.Generic.List[object]

  foreach ($seed in $Seeds) {
    Write-Host ""
    Write-Host ("=== R2.1-e eval seed {0} ===" -f $seed) -ForegroundColor Cyan

    $before = Get-LatestReportPath -ReportsDir $reportsDir
    python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed $seed
    $evalExit = $LASTEXITCODE
    if ($evalExit -ne 0) {
      throw ("Eval fallo para seed={0} (exit={1})" -f $seed, $evalExit)
    }

    $after = Get-LatestReportPath -ReportsDir $reportsDir
    if ([string]::IsNullOrWhiteSpace($after)) {
      throw ("No se encontro reporte tras eval seed={0}" -f $seed)
    }
    if ($before -and ($before -eq $after)) {
      Write-Warning ("No cambio ruta de reporte para seed={0}; se usara el ultimo disponible: {1}" -f $seed, $after)
    }

    Write-Host ("Gate report path: {0}" -f $after)
    & $gateScript `
      -ReportPath $after `
      -Side $Side `
      -Scenario $Scenario `
      -CaptureMetric $CaptureMetric `
      -MinCaptureAttemptSuccessRate $MinCaptureAttemptSuccessRate `
      -MaxLossRate $MaxLossRate `
      -MinVpEntryConversionRate $MinVpEntryConversionRate
    $gateExit = $LASTEXITCODE

    $results.Add([pscustomobject]@{
      seed = $seed
      report = $after
      gate = $(if ($gateExit -eq 0) { "PASS" } else { "FAIL" })
    }) | Out-Null
    $row = Get-ReportGateMetrics -ReportPath $after -Side $Side -Scenario $Scenario -CaptureMetric $CaptureMetric
    if ($null -ne $row) {
      $metricRows.Add([pscustomobject]@{
        seed = $seed
        capture_metric_value = [double]$row.capture_metric_value
        loss_rate = [double]$row.loss_rate
        vp_entry_conversion_rate = [double]$row.vp_entry_conversion_rate
      }) | Out-Null
    }
  }

  Write-Host ""
  Write-Host "=== R2.1-e Gate Summary ===" -ForegroundColor Cyan
  $results | Format-Table -AutoSize

  $failed = @($results | Where-Object { $_.gate -eq "FAIL" }).Count
  $passed = [int]$results.Count - [int]$failed
  $policyOk = $false
  $policyMsg = ""

  if ($PassPolicy -eq "strict") {
    $policyOk = ($failed -eq 0)
    $policyMsg = ("strict: requires {0}/{0} PASS, got {1}/{0}" -f $results.Count, $passed)
  } elseif ($PassPolicy -eq "majority") {
    $needed = [int][Math]::Ceiling([double]$results.Count / 2.0)
    $policyOk = ($passed -ge $needed)
    $policyMsg = ("majority: requires >= {0}/{1} PASS, got {2}/{1}" -f $needed, $results.Count, $passed)
  } elseif ($PassPolicy -eq "mean") {
    if ($metricRows.Count -lt 1) {
      $policyOk = $false
      $policyMsg = "mean: no metric rows available"
    } else {
      $avgCapture = ($metricRows | Measure-Object -Property capture_metric_value -Average).Average
      $avgLoss = ($metricRows | Measure-Object -Property loss_rate -Average).Average
      $avgVp = ($metricRows | Measure-Object -Property vp_entry_conversion_rate -Average).Average
      $okCapture = ($avgCapture -gt $MinCaptureAttemptSuccessRate)
      $okLoss = ($avgLoss -lt $MaxLossRate)
      $okVp = ($avgVp -ge $MinVpEntryConversionRate)
      $policyOk = ($okCapture -and $okLoss -and $okVp)
      $policyMsg = (
        "mean: {0}={1:N4} [{2}] loss_rate={3:N4} [{4}] vp_entry_conversion_rate={5:N4} [{6}]" -f
        $CaptureMetric, $avgCapture, $(if ($okCapture) { "PASS" } else { "FAIL" }),
        $avgLoss, $(if ($okLoss) { "PASS" } else { "FAIL" }),
        $avgVp, $(if ($okVp) { "PASS" } else { "FAIL" })
      )
    }
  }

  Write-Host ("Policy: {0}" -f $PassPolicy)
  Write-Host $policyMsg

  if (-not $policyOk) {
    Write-Host ("RESULT: FAIL ({0}/{1} seeds failed under policy='{2}')" -f $failed, $results.Count, $PassPolicy) -ForegroundColor Red
    exit 1
  }

  Write-Host ("RESULT: PASS ({0}/{1} seeds passed under policy='{2}')" -f $passed, $results.Count, $PassPolicy) -ForegroundColor Green
  exit 0
}
finally {
  Pop-Location
}

