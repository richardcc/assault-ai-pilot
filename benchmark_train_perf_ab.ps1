param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$SecondsPerRun = 180,
  [string]$LabelA = "A",
  [string]$LabelB = "B"
)

Set-Location $Repo
.\.venv\Scripts\Activate.ps1

$env:ASSAULT_PERF_PROFILE = "1"
$env:ASSAULT_PERF_EVERY = "50"

function Run-Benchmark([string]$Label) {
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  $log = Join-Path $Repo "bench_${Label}_$ts.log"
  Write-Host "== RUN $Label =="
  Write-Host "Log: $log"

  $cmd = "set ASSAULT_PERF_PROFILE=1 && set ASSAULT_PERF_EVERY=50 && set PYTHONUNBUFFERED=1 && python -u -m assault_sim.train.train_sb3 > `"$log`" 2>&1"
  $p = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c $cmd" `
    -WorkingDirectory $Repo `
    -PassThru

  Start-Sleep -Seconds $SecondsPerRun

  if (-not $p.HasExited) {
    Stop-Process -Id $p.Id -Force
  }

  Write-Host "== END $Label =="
  Write-Host ""
  return $log
}

function Get-LogStats([string]$LogPath) {
  $lines = Get-Content -Path $LogPath

  $fpsVals = @()
  foreach ($line in $lines) {
    if ($line -match "fps\s*\|\s*([0-9]+(?:\.[0-9]+)?)") {
      $fpsVals += [double]$Matches[1]
    }
  }
  $fpsAvg = if ($fpsVals.Count -gt 0) {
    ($fpsVals | Measure-Object -Average).Average
  } else { [double]0.0 }

  $perfLines = $lines | Select-String -Pattern "\[PERF\]\[GymAssaultEnv\]"
  $ctrlVals = @()
  $execVals = @()
  $stepVals = @()
  foreach ($m in $perfLines) {
    $ln = $m.Line
    if ($ln -match "controller_act_avg_ms=([0-9]+(?:\.[0-9]+)?)") {
      $ctrlVals += [double]$Matches[1]
    }
    if ($ln -match "executor_avg_ms=([0-9]+(?:\.[0-9]+)?)") {
      $execVals += [double]$Matches[1]
    }
    if ($ln -match "step_avg_ms=([0-9]+(?:\.[0-9]+)?)") {
      $stepVals += [double]$Matches[1]
    }
  }

  $ctrlAvg = if ($ctrlVals.Count -gt 0) { ($ctrlVals | Measure-Object -Average).Average } else { [double]0.0 }
  $execAvg = if ($execVals.Count -gt 0) { ($execVals | Measure-Object -Average).Average } else { [double]0.0 }
  $stepAvg = if ($stepVals.Count -gt 0) { ($stepVals | Measure-Object -Average).Average } else { [double]0.0 }

  return [PSCustomObject]@{
    LogPath = $LogPath
    FpsAvg = [math]::Round($fpsAvg, 2)
    StepAvgMs = [math]::Round($stepAvg, 2)
    ControllerAvgMs = [math]::Round($ctrlAvg, 2)
    ExecutorAvgMs = [math]::Round($execAvg, 2)
    FpsSamples = $fpsVals.Count
    PerfSamples = $perfLines.Count
  }
}

Write-Host "A/B benchmark starting..."
Write-Host "Each run duration: $SecondsPerRun seconds"
Write-Host ""

Write-Host ">>> Prepare state for RUN $LabelA, then press ENTER..."
Read-Host | Out-Null
$logA = Run-Benchmark $LabelA
$statsA = Get-LogStats $logA

Write-Host ">>> Prepare state for RUN $LabelB, then press ENTER..."
Read-Host | Out-Null
$logB = Run-Benchmark $LabelB
$statsB = Get-LogStats $logB

$fpsDelta = [math]::Round(($statsB.FpsAvg - $statsA.FpsAvg), 2)
$fpsDeltaPct = if ($statsA.FpsAvg -ne 0) { [math]::Round((($statsB.FpsAvg / $statsA.FpsAvg) - 1.0) * 100.0, 2) } else { 0.0 }
$ctrlDelta = [math]::Round(($statsB.ControllerAvgMs - $statsA.ControllerAvgMs), 2)
$execDelta = [math]::Round(($statsB.ExecutorAvgMs - $statsA.ExecutorAvgMs), 2)
$stepDelta = [math]::Round(($statsB.StepAvgMs - $statsA.StepAvgMs), 2)

Write-Host ""
Write-Host "===== A/B RESULT ====="
$statsA | Format-List
$statsB | Format-List
Write-Host "Delta B-A: fps=$fpsDelta (${fpsDeltaPct}%), step_avg_ms=$stepDelta, controller_avg_ms=$ctrlDelta, executor_avg_ms=$execDelta"

# Uncomment if you want to clear env vars after benchmark:
# Remove-Item Env:ASSAULT_PERF_PROFILE -ErrorAction SilentlyContinue
# Remove-Item Env:ASSAULT_PERF_EVERY -ErrorAction SilentlyContinue
