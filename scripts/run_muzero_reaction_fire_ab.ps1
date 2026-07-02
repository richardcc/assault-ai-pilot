[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [ValidateSet("fast", "test", "quality")]
  [string]$Profile = "test",
  [switch]$OpenViewer
)

$ErrorActionPreference = "Stop"

function Get-LatestMuZeroRunId {
  param([string]$RepoRoot)
  $runsRoot = Join-Path $RepoRoot "runs"
  if (-not (Test-Path -LiteralPath $runsRoot)) {
    return ""
  }
  $latest = Get-ChildItem -Path $runsRoot -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latest) {
    return ""
  }
  return [string]$latest.Name
}

function Get-MuZeroBenchRow {
  param([object]$BenchJson)
  if ($null -eq $BenchJson -or $null -eq $BenchJson.results) {
    return $null
  }
  $row = $BenchJson.results | Where-Object { $_.agent_name -eq "muzero_stub" } | Select-Object -First 1
  if ($null -eq $row) {
    $row = $BenchJson.results | Select-Object -First 1
  }
  return $row
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $abDir = Join-Path $Repo ("runs\reaction_fire_ab\" + $stamp)
  New-Item -ItemType Directory -Path $abDir -Force | Out-Null

  $modes = @(
    @{ Name = "on"; Value = "1" },
    @{ Name = "off"; Value = "0" }
  )
  $summaryRows = @()
  $totalSw = [System.Diagnostics.Stopwatch]::StartNew()

  foreach ($mode in $modes) {
    $modeName = [string]$mode.Name
    $modeValue = [string]$mode.Value
    Write-Host ""
    Write-Host ("== Reaction Fire " + $modeName.ToUpper() + " ==")
    $env:ASSAULT_ENABLE_REACTION_FIRE = $modeValue
    Write-Host ("ASSAULT_ENABLE_REACTION_FIRE=" + $modeValue)
    $beforeRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
    $modeSw = [System.Diagnostics.Stopwatch]::StartNew()

    $runner = ".\scripts\run_muzero_train_and_bench.ps1"
    if ($OpenViewer -and $modeName -eq "off") {
      & $runner -Repo $Repo -Profile $Profile -OpenViewer
    } else {
      & $runner -Repo $Repo -Profile $Profile
    }
    if ($LASTEXITCODE -ne 0) {
      throw ("MuZero train+bench failed for mode=" + $modeName + " exit=" + $LASTEXITCODE)
    }
    $modeSw.Stop()

    $afterRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
    if ([string]::IsNullOrWhiteSpace($afterRunId) -or $afterRunId -eq $beforeRunId) {
      throw ("Could not detect new MuZero run_id for mode=" + $modeName)
    }

    $benchLatestPath = Join-Path $Repo "runs\bench_latest.json"
    if (-not (Test-Path -LiteralPath $benchLatestPath)) {
      throw "Missing runs\bench_latest.json after benchmark."
    }
    $benchCopyPath = Join-Path $abDir ("bench_" + $modeName + ".json")
    Copy-Item -LiteralPath $benchLatestPath -Destination $benchCopyPath -Force

    $benchJson = Get-Content -LiteralPath $benchCopyPath -Raw | ConvertFrom-Json
    $mz = Get-MuZeroBenchRow -BenchJson $benchJson
    $trackedAvg = 0.0
    if ($null -ne $mz -and $null -ne $mz.tracked_captured_avg) {
      $trackedAvg = [double]$mz.tracked_captured_avg
    }
    $summaryRows += [pscustomobject]@{
      mode = $modeName
      profile = $Profile
      run_id = $afterRunId
      win_rate = [double]($mz.win_rate)
      avg_return = [double]($mz.avg_return)
      avg_steps = [double]($mz.avg_steps)
      tracked_captured_avg = $trackedAvg
      elapsed_s = [double]$modeSw.Elapsed.TotalSeconds
      bench_json = (Resolve-Path $benchCopyPath).Path
    }
  }

  $totalSw.Stop()
  $summaryPath = Join-Path $abDir "summary.json"
  ($summaryRows | ConvertTo-Json -Depth 6) | Out-File -LiteralPath $summaryPath -Encoding utf8

  Write-Host ""
  Write-Host "== Reaction Fire A/B Summary =="
  $summaryRows | Format-Table mode, profile, run_id, win_rate, avg_return, avg_steps, tracked_captured_avg, elapsed_s -AutoSize | Out-String | Write-Host
  Write-Host ("Summary JSON: " + $summaryPath)
  Write-Host ("Total elapsed: {0:n1}s" -f $totalSw.Elapsed.TotalSeconds)
}
finally {
  Remove-Item Env:ASSAULT_ENABLE_REACTION_FIRE -ErrorAction SilentlyContinue
  Pop-Location
}
