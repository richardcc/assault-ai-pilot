param(
  [string]$Repo = "C:\repos\python\assault",
  [Parameter(Mandatory = $true)][string]$BaselineCheckpoint,
  [Parameter(Mandatory = $true)][string]$CandidateCheckpoint,
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.yaml",
  [string]$BaselineConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.q_calib_a.yaml",
  [string]$CandidateConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.q_calib_a_vp_push.yaml",
  [double]$MinVpTakeRateGain = 0.05,
  [double]$MaxTimeoutRateDelta = 0.03,
  [double]$MaxCandidateTimeoutRate = 0.20
)

$ErrorActionPreference = "Stop"

function Get-FirstRow([object]$payload) {
  if ($null -ne $payload.results -and $payload.results.Count -gt 0) { return $payload.results[0] }
  if ($null -ne $payload.rows -and $payload.rows.Count -gt 0) { return $payload.rows[0] }
  throw "No benchmark rows found in payload."
}

function Get-MetricOrDefault([object]$row, [string]$name, [double]$defaultValue = 0.0) {
  $v = $row.$name
  if ($null -eq $v) { return [double]$defaultValue }
  return [double]$v
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $outDir = Join-Path $Repo "runs\bench_compare"
  if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
  }
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $baseOut = Join-Path $outDir ("bench_a_{0}.json" -f $stamp)
  $candOut = Join-Path $outDir ("bench_vp_push_{0}.json" -f $stamp)

  Write-Host "== BENCH BASELINE A =="
  python -m assault_bench.runner `
    --config $BenchConfig `
    --checkpoint $BaselineCheckpoint `
    --muzero-config $BaselineConfig
  if ($LASTEXITCODE -ne 0) { throw "Baseline bench failed with exit code $LASTEXITCODE" }
  Copy-Item -Path "runs\bench_latest.json" -Destination $baseOut -Force

  Write-Host "== BENCH CANDIDATE VP PUSH =="
  python -m assault_bench.runner `
    --config $BenchConfig `
    --checkpoint $CandidateCheckpoint `
    --muzero-config $CandidateConfig
  if ($LASTEXITCODE -ne 0) { throw "Candidate bench failed with exit code $LASTEXITCODE" }
  Copy-Item -Path "runs\bench_latest.json" -Destination $candOut -Force

  $basePayload = Get-Content -Path $baseOut -Raw | ConvertFrom-Json
  $candPayload = Get-Content -Path $candOut -Raw | ConvertFrom-Json
  $baseRow = Get-FirstRow $basePayload
  $candRow = Get-FirstRow $candPayload

  $baseTimeout = Get-MetricOrDefault $baseRow "timeout_rate"
  $candTimeout = Get-MetricOrDefault $candRow "timeout_rate"
  $baseCaptured = Get-MetricOrDefault $baseRow "tracked_captured_avg"
  $candCaptured = Get-MetricOrDefault $candRow "tracked_captured_avg"
  $baseTakeRate = Get-MetricOrDefault $baseRow "xai_vp_capture_take_rate"
  $candTakeRate = Get-MetricOrDefault $candRow "xai_vp_capture_take_rate"

  $takeRateDelta = $candTakeRate - $baseTakeRate
  $timeoutDelta = $candTimeout - $baseTimeout
  $capturedDelta = $candCaptured - $baseCaptured

  $promote = (
    ($takeRateDelta -ge $MinVpTakeRateGain) -and
    ($timeoutDelta -le $MaxTimeoutRateDelta) -and
    ($candTimeout -le $MaxCandidateTimeoutRate)
  )

  $summary = [ordered]@{
    baseline_file = $baseOut
    candidate_file = $candOut
    baseline = [ordered]@{
      timeout_rate = $baseTimeout
      tracked_captured_avg = $baseCaptured
      xai_vp_capture_take_rate = $baseTakeRate
    }
    candidate = [ordered]@{
      timeout_rate = $candTimeout
      tracked_captured_avg = $candCaptured
      xai_vp_capture_take_rate = $candTakeRate
    }
    deltas_candidate_minus_baseline = [ordered]@{
      timeout_rate = $timeoutDelta
      tracked_captured_avg = $capturedDelta
      xai_vp_capture_take_rate = $takeRateDelta
    }
    thresholds = [ordered]@{
      min_vp_take_rate_gain = $MinVpTakeRateGain
      max_timeout_rate_delta = $MaxTimeoutRateDelta
      max_candidate_timeout_rate = $MaxCandidateTimeoutRate
    }
    decision = if ($promote) { "PROMOTE" } else { "HOLD" }
  }

  $summaryPath = Join-Path $outDir ("compare_a_vs_vp_push_{0}.json" -f $stamp)
  ($summary | ConvertTo-Json -Depth 8) | Set-Content -Path $summaryPath -Encoding UTF8

  Write-Host ""
  Write-Host "== COMPARISON SUMMARY =="
  Write-Host ($summary | ConvertTo-Json -Depth 8)
  Write-Host "Summary file: $summaryPath"
}
finally {
  Pop-Location
}
