[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(7, 13, 29)
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

function Get-BenchRow {
  param(
    [object]$BenchJson,
    [string]$AgentName
  )
  if ($null -eq $BenchJson -or $null -eq $BenchJson.results) {
    return $null
  }
  return ($BenchJson.results | Where-Object { $_.agent_name -eq $AgentName } | Select-Object -First 1)
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $outDir = Join-Path $Repo ("runs\smoke_ab3\" + $stamp)
  New-Item -ItemType Directory -Path $outDir -Force | Out-Null

  $baseTrainCfg = Join-Path $Repo "agents/muzero/configs/muzero_config.smoke.yaml"
  $baseBenchCfg = Join-Path $Repo "assault_bench/configs/benchmark_config.smoke.yaml"
  if (-not (Test-Path -LiteralPath $baseTrainCfg)) { throw "Missing $baseTrainCfg" }
  if (-not (Test-Path -LiteralPath $baseBenchCfg)) { throw "Missing $baseBenchCfg" }

  $rows = @()
  $totalSw = [System.Diagnostics.Stopwatch]::StartNew()

  foreach ($seed in $Seeds) {
    Write-Host ""
    Write-Host ("== Smoke repetition seed={0} ==" -f $seed)
    $beforeRunId = Get-LatestMuZeroRunId -RepoRoot $Repo

    $tmpTrainCfg = Join-Path $outDir ("muzero_config.seed_" + $seed + ".yaml")
    $tmpBenchCfg = Join-Path $outDir ("benchmark_config.seed_" + $seed + ".yaml")

    $trainLines = Get-Content -LiteralPath $baseTrainCfg
    $seedReplaced = $false
    for ($i = 0; $i -lt $trainLines.Count; $i += 1) {
      if (-not $seedReplaced -and $trainLines[$i] -match '^\s*seed:\s*\d+\s*$') {
        $indent = ([regex]::Match($trainLines[$i], '^\s*')).Value
        $trainLines[$i] = ("{0}seed: {1}" -f $indent, [int]$seed)
        $seedReplaced = $true
      }
    }
    if (-not $seedReplaced) {
      throw ("Could not locate scenario.seed in " + $baseTrainCfg)
    }
    Set-Content -LiteralPath $tmpTrainCfg -Value ($trainLines -join "`r`n") -Encoding utf8

    Copy-Item -LiteralPath $baseBenchCfg -Destination $tmpBenchCfg -Force

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    & ".\scripts\run_muzero_train_and_bench.ps1" `
      -Repo $Repo `
      -Profile smoke `
      -TrainConfig $tmpTrainCfg `
      -MuZeroConfig $tmpTrainCfg `
      -BenchConfig $tmpBenchCfg
    if ($LASTEXITCODE -ne 0) {
      throw ("run_muzero_train_and_bench failed for seed={0} exit={1}" -f $seed, $LASTEXITCODE)
    }
    $sw.Stop()

    $afterRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
    if ([string]::IsNullOrWhiteSpace($afterRunId) -or $afterRunId -eq $beforeRunId) {
      throw ("Could not detect new MuZero run_id for seed={0}" -f $seed)
    }

    $benchPath = Join-Path $Repo "runs\bench_latest.json"
    if (-not (Test-Path -LiteralPath $benchPath)) {
      throw "Missing runs\bench_latest.json after benchmark."
    }
    $benchCopy = Join-Path $outDir ("bench_seed_" + $seed + ".json")
    Copy-Item -LiteralPath $benchPath -Destination $benchCopy -Force
    $benchJson = Get-Content -LiteralPath $benchCopy -Raw | ConvertFrom-Json

    $rowUS = Get-BenchRow -BenchJson $benchJson -AgentName "muzero_vs_random_US"
    $rowIT = Get-BenchRow -BenchJson $benchJson -AgentName "muzero_vs_random_IT"

    $rows += [pscustomobject]@{
      seed = [int]$seed
      run_id = [string]$afterRunId
      us_win_rate = [double]($rowUS.win_rate)
      us_timeout_rate = [double]($rowUS.timeout_rate)
      us_tracked_captured_avg = [double]($rowUS.tracked_captured_avg)
      it_win_rate = [double]($rowIT.win_rate)
      it_timeout_rate = [double]($rowIT.timeout_rate)
      it_tracked_captured_avg = [double]($rowIT.tracked_captured_avg)
      elapsed_s = [double]$sw.Elapsed.TotalSeconds
      bench_json = (Resolve-Path $benchCopy).Path
    }
  }

  $totalSw.Stop()
  $summaryPath = Join-Path $outDir "summary.json"
  ($rows | ConvertTo-Json -Depth 6) | Out-File -LiteralPath $summaryPath -Encoding utf8

  $agg = [pscustomobject]@{
    reps = [int]$rows.Count
    us_win_rate_mean = [double](($rows | Measure-Object -Property us_win_rate -Average).Average)
    us_timeout_rate_mean = [double](($rows | Measure-Object -Property us_timeout_rate -Average).Average)
    us_tracked_captured_avg_mean = [double](($rows | Measure-Object -Property us_tracked_captured_avg -Average).Average)
    it_win_rate_mean = [double](($rows | Measure-Object -Property it_win_rate -Average).Average)
    it_timeout_rate_mean = [double](($rows | Measure-Object -Property it_timeout_rate -Average).Average)
    it_tracked_captured_avg_mean = [double](($rows | Measure-Object -Property it_tracked_captured_avg -Average).Average)
    total_elapsed_s = [double]$totalSw.Elapsed.TotalSeconds
  }
  $aggPath = Join-Path $outDir "summary_aggregate.json"
  ($agg | ConvertTo-Json -Depth 6) | Out-File -LiteralPath $aggPath -Encoding utf8

  Write-Host ""
  Write-Host "== MuZero Smoke AB3 Summary =="
  $rows | Format-Table seed, run_id, us_win_rate, us_timeout_rate, us_tracked_captured_avg, it_win_rate, it_timeout_rate, it_tracked_captured_avg, elapsed_s -AutoSize | Out-String | Write-Host
  Write-Host ""
  Write-Host "== Aggregate Means =="
  $agg | Format-List | Out-String | Write-Host
  Write-Host ("Summary JSON: " + $summaryPath)
  Write-Host ("Aggregate JSON: " + $aggPath)
}
finally {
  Pop-Location
}
