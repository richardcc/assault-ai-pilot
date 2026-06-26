param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$SecondsPerRun = 180
)

Set-Location $Repo
.\.venv\Scripts\Activate.ps1

# Consistent perf logs for run-to-run comparison
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

# Single benchmark run for current code state
$logCurrent = Run-Benchmark "current"

Write-Host "Quick summary:"
Write-Host "--------------"
Select-String -Path $logCurrent -Pattern "fps|PERF\]\[GymAssaultEnv" | ForEach-Object { $_.Line }

# Uncomment if you want to clear perf env vars after run
# Remove-Item Env:ASSAULT_PERF_PROFILE -ErrorAction SilentlyContinue
# Remove-Item Env:ASSAULT_PERF_EVERY -ErrorAction SilentlyContinue
