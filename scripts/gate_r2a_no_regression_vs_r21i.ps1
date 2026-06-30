param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [switch]$RunEval,
  [int]$Episodes = 20,
  [int]$Seed = 42,
  [double]$MaxLossRateDelta = 0.05,
  [double]$MaxTrueWinRateDrop = 0.05,
  [double]$MaxVpEntryConversionDrop = 0.10,
  [double]$MaxCaptureConversionDrop = 0.10
)

$ErrorActionPreference = "Stop"

function Resolve-PathStrict {
  param([string]$PathText)
  if (-not (Test-Path -Path $PathText -PathType Leaf)) {
    throw "Archivo no encontrado: $PathText"
  }
  return (Resolve-Path $PathText).Path
}

function Get-LatestReportPath {
  param([string]$ReportsDir)
  $latest = Get-ChildItem -Path $ReportsDir -File -Filter "metrics_sb3_report_*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latest) { return $null }
  return $latest.FullName
}

function Get-ScenarioMetricsFromReport {
  param(
    [string]$ReportPath,
    [string]$Side,
    [string]$Scenario
  )
  $report = Get-Content $ReportPath -Raw | ConvertFrom-Json
  $payload = $report.by_side_and_scenario.$Side.$Scenario
  if ($null -eq $payload) {
    throw "No se encontro side/scenario en $ReportPath (side=$Side scenario=$Scenario)"
  }
  $summary = $payload.summary
  $mission = $payload.mission
  if ($null -eq $summary -or $null -eq $mission) {
    throw "Reporte sin bloques summary/mission: $ReportPath"
  }
  return [pscustomobject]@{
    report_path = $ReportPath
    true_win_rate = [double]($summary.true_win_rate)
    loss_rate = [double]($summary.loss_rate)
    vp_entry_conversion_rate = [double]($mission.vp_entry_conversion_rate)
    capture_conversion_after_contact = [double]($mission.capture_conversion_after_contact)
  }
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $reportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
  if (-not (Test-Path -Path $reportsDir -PathType Container)) {
    throw "No existe carpeta de reportes: $reportsDir"
  }

  $baselinePath = Get-LatestReportPath -ReportsDir $reportsDir
  if ([string]::IsNullOrWhiteSpace($baselinePath)) {
    throw "No se encontro baseline en $reportsDir"
  }
  $baselinePaths = @($baselinePath)
  $baseline = Get-ScenarioMetricsFromReport -ReportPath $baselinePath -Side $Side -Scenario $Scenario

  $before = Get-LatestReportPath -ReportsDir $reportsDir
  if ($RunEval) {
    Write-Host "=== Running eval before no-regression gate ===" -ForegroundColor Cyan
    python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed $Seed
    if ($LASTEXITCODE -ne 0) {
      throw "eval_sb3 fallo (episodes=$Episodes seed=$Seed exit=$LASTEXITCODE)"
    }
  }
  $currentPath = Get-LatestReportPath -ReportsDir $reportsDir
  if ([string]::IsNullOrWhiteSpace($currentPath)) {
    throw "No se encontro reporte actual para gate de no-regresion."
  }
  if ($RunEval -and $before -and $before -eq $currentPath) {
    Write-Warning "No cambio la ruta del reporte tras eval; se usara el ultimo disponible."
  }
  $current = Get-ScenarioMetricsFromReport -ReportPath $currentPath -Side $Side -Scenario $Scenario

  $deltaTrueWin = [double]$current.true_win_rate - [double]$baseline.true_win_rate
  $deltaLoss = [double]$current.loss_rate - [double]$baseline.loss_rate
  $deltaVpConv = [double]$current.vp_entry_conversion_rate - [double]$baseline.vp_entry_conversion_rate
  $deltaCaptureConv = [double]$current.capture_conversion_after_contact - [double]$baseline.capture_conversion_after_contact

  $gateTrueWin = ($deltaTrueWin -ge (-1.0 * $MaxTrueWinRateDrop))
  $gateLoss = ($deltaLoss -le $MaxLossRateDelta)
  $gateVpConv = ($deltaVpConv -ge (-1.0 * $MaxVpEntryConversionDrop))
  $gateCaptureConv = ($deltaCaptureConv -ge (-1.0 * $MaxCaptureConversionDrop))
  $gateAll = $gateTrueWin -and $gateLoss -and $gateVpConv -and $gateCaptureConv

  Write-Host ""
  Write-Host "=== R2.a no-regression gate vs latest baseline ===" -ForegroundColor Cyan
  Write-Host ("Baseline reports: {0}" -f ($baselinePaths -join " | "))
  Write-Host ("Current report:   {0}" -f $current.report_path)
  Write-Host ("Filters: side={0}; scenario={1}" -f $Side, $Scenario)
  Write-Host ""

  $rows = @(
    [pscustomobject]@{
      metric = "true_win_rate"
      baseline = [math]::Round([double]$baseline.true_win_rate, 4)
      current = [math]::Round([double]$current.true_win_rate, 4)
      delta = [math]::Round($deltaTrueWin, 4)
      threshold = ">=" + (-1.0 * $MaxTrueWinRateDrop).ToString("N4")
      gate = $(if ($gateTrueWin) { "PASS" } else { "FAIL" })
    },
    [pscustomobject]@{
      metric = "loss_rate"
      baseline = [math]::Round([double]$baseline.loss_rate, 4)
      current = [math]::Round([double]$current.loss_rate, 4)
      delta = [math]::Round($deltaLoss, 4)
      threshold = "<=" + $MaxLossRateDelta.ToString("N4")
      gate = $(if ($gateLoss) { "PASS" } else { "FAIL" })
    },
    [pscustomobject]@{
      metric = "vp_entry_conversion_rate"
      baseline = [math]::Round([double]$baseline.vp_entry_conversion_rate, 4)
      current = [math]::Round([double]$current.vp_entry_conversion_rate, 4)
      delta = [math]::Round($deltaVpConv, 4)
      threshold = ">=" + (-1.0 * $MaxVpEntryConversionDrop).ToString("N4")
      gate = $(if ($gateVpConv) { "PASS" } else { "FAIL" })
    },
    [pscustomobject]@{
      metric = "capture_conversion_after_contact"
      baseline = [math]::Round([double]$baseline.capture_conversion_after_contact, 4)
      current = [math]::Round([double]$current.capture_conversion_after_contact, 4)
      delta = [math]::Round($deltaCaptureConv, 4)
      threshold = ">=" + (-1.0 * $MaxCaptureConversionDrop).ToString("N4")
      gate = $(if ($gateCaptureConv) { "PASS" } else { "FAIL" })
    }
  )
  $rows | Format-Table -AutoSize

  Write-Host ""
  if (-not $gateAll) {
    Write-Host "RESULT: FAIL (hay regresion material vs baseline R2.1-i)." -ForegroundColor Red
    exit 1
  }
  Write-Host "RESULT: PASS (sin regresion material vs baseline R2.1-i)." -ForegroundColor Green
  exit 0
}
finally {
  Pop-Location
}
