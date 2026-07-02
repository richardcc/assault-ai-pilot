[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(7, 13, 29),
  [double]$ObjectiveLossWeightOff = 0.0,
  [double]$ObjectiveLossWeightOn = 0.25,
  [int]$TrainIterations = 5,
  [int]$EpisodesPerIter = 4
)

$ErrorActionPreference = "Stop"

function Get-LatestMuZeroRunId {
  param([string]$RepoRoot)
  $runsRoot = Join-Path $RepoRoot "runs"
  if (-not (Test-Path -LiteralPath $runsRoot)) { return "" }
  $latest = Get-ChildItem -Path $runsRoot -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latest) { return "" }
  return [string]$latest.Name
}

function Get-BenchRow {
  param([object]$BenchJson, [string]$AgentName)
  if ($null -eq $BenchJson -or $null -eq $BenchJson.results) { return $null }
  return ($BenchJson.results | Where-Object { $_.agent_name -eq $AgentName } | Select-Object -First 1)
}

function Build-TempConfigWithOverrides {
  param(
    [string]$BaseConfigPath,
    [string]$OutputPath,
    [int]$Seed,
    [double]$ObjectiveLossWeight,
    [int]$Iterations,
    [int]$Episodes
  )

  $lines = Get-Content -LiteralPath $BaseConfigPath
  $seedReplaced = $false
  $objReplaced = $false
  $iterReplaced = $false
  $epiReplaced = $false
  $inTrain = $false
  $outLines = @()

  foreach ($line in $lines) {
    if ($line -match '^\s*train:\s*$') {
      $inTrain = $true
      $outLines += $line
      continue
    }
    if ($line -match '^\S' -and $line -notmatch '^\s*#') {
      $inTrain = $false
    }

    if (-not $seedReplaced -and $line -match '^\s*seed:\s*\d+\s*$') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}seed: {1}" -f $indent, [int]$Seed)
      $seedReplaced = $true
      continue
    }
    if (-not $objReplaced -and $line -match '^\s*objective_loss_weight\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}objective_loss_weight: {1}" -f $indent, [string]$ObjectiveLossWeight)
      $objReplaced = $true
      continue
    }
    if ($inTrain -and -not $iterReplaced -and $line -match '^\s*iterations:\s*\d+\s*$') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}iterations: {1}" -f $indent, [int]$Iterations)
      $iterReplaced = $true
      continue
    }
    if ($inTrain -and -not $epiReplaced -and $line -match '^\s*episodes_per_iter:\s*\d+\s*$') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}episodes_per_iter: {1}" -f $indent, [int]$Episodes)
      $epiReplaced = $true
      continue
    }
    $outLines += $line
  }

  if (-not $seedReplaced) { throw ("Could not locate scenario.seed in config: " + $BaseConfigPath) }
  if (-not $objReplaced) { throw ("Could not locate train.objective_loss_weight in config: " + $BaseConfigPath) }
  if (-not $iterReplaced) { throw ("Could not locate train.iterations in config: " + $BaseConfigPath) }
  if (-not $epiReplaced) { throw ("Could not locate train.episodes_per_iter in config: " + $BaseConfigPath) }

  Set-Content -LiteralPath $OutputPath -Value ($outLines -join "`r`n") -Encoding utf8
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") { . .\.venv\Scripts\Activate.ps1 }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $outDir = Join-Path $Repo ("runs\objective_head_ab3\" + $stamp)
  New-Item -ItemType Directory -Path $outDir -Force | Out-Null

  $baseTrainCfg = Join-Path $Repo "agents/muzero/configs/muzero_config.smoke.yaml"
  $baseBenchCfg = Join-Path $Repo "assault_bench/configs/benchmark_config.smoke.yaml"
  if (-not (Test-Path -LiteralPath $baseTrainCfg)) { throw "Missing $baseTrainCfg" }
  if (-not (Test-Path -LiteralPath $baseBenchCfg)) { throw "Missing $baseBenchCfg" }

  $rows = @()
  $totalSw = [System.Diagnostics.Stopwatch]::StartNew()

  foreach ($seed in $Seeds) {
    foreach ($mode in @(
      @{ label = "off"; weight = [double]$ObjectiveLossWeightOff },
      @{ label = "on"; weight = [double]$ObjectiveLossWeightOn }
    )) {
      $label = [string]$mode.label
      $weight = [double]$mode.weight
      Write-Host ""
      Write-Host ("== Objective head AB3 | mode={0} seed={1} weight={2} iter={3} epi={4} ==" -f $label, $seed, $weight, $TrainIterations, $EpisodesPerIter)

      $beforeRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
      $tmpTrainCfg = Join-Path $outDir ("muzero_config." + $label + ".seed_" + $seed + ".yaml")
      Build-TempConfigWithOverrides `
        -BaseConfigPath $baseTrainCfg `
        -OutputPath $tmpTrainCfg `
        -Seed ([int]$seed) `
        -ObjectiveLossWeight ([double]$weight) `
        -Iterations ([int]$TrainIterations) `
        -Episodes ([int]$EpisodesPerIter)

      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      & ".\scripts\run_muzero_train_and_bench.ps1" `
        -Repo $Repo `
        -Profile smoke `
        -TrainConfig $tmpTrainCfg `
        -MuZeroConfig $tmpTrainCfg `
        -BenchConfig $baseBenchCfg
      if ($LASTEXITCODE -ne 0) {
        throw ("run_muzero_train_and_bench failed for mode={0} seed={1} exit={2}" -f $label, $seed, $LASTEXITCODE)
      }
      $sw.Stop()

      $afterRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
      if ([string]::IsNullOrWhiteSpace($afterRunId) -or $afterRunId -eq $beforeRunId) {
        throw ("Could not detect new MuZero run_id for mode={0} seed={1}" -f $label, $seed)
      }

      $benchPath = Join-Path $Repo "runs\bench_latest.json"
      if (-not (Test-Path -LiteralPath $benchPath)) { throw "Missing runs\bench_latest.json after benchmark." }
      $benchCopy = Join-Path $outDir ("bench_" + $label + "_seed_" + $seed + ".json")
      Copy-Item -LiteralPath $benchPath -Destination $benchCopy -Force
      $benchJson = Get-Content -LiteralPath $benchCopy -Raw | ConvertFrom-Json
      $rowUS = Get-BenchRow -BenchJson $benchJson -AgentName "muzero_vs_random_US"
      $rowIT = Get-BenchRow -BenchJson $benchJson -AgentName "muzero_vs_random_IT"

      $unitsSidesPath = Join-Path $Repo ("runs\" + $afterRunId + "\metrics\units_sides.json")
      if (-not (Test-Path -LiteralPath $unitsSidesPath)) { throw ("Missing units_sides metrics: " + $unitsSidesPath) }
      $unitsJson = Get-Content -LiteralPath $unitsSidesPath -Raw | ConvertFrom-Json
      $opf = $unitsJson.diagnostics_summary.objective_progress_funnel

      $rows += [pscustomobject]@{
        mode = [string]$label
        seed = [int]$seed
        objective_loss_weight = [double]$weight
        run_id = [string]$afterRunId
        objective_progress_rate = [double]$opf.global.progress_rate
        objective_conversion_rate = [double]$opf.global.conversion_rate
        objective_avg_progress_delta = [double]$opf.global.avg_progress_delta
        objective_opportunities = [int]$opf.global.opportunities
        us_conversion_rate = [double]$opf.by_side.US.conversion_rate
        it_conversion_rate = [double]$opf.by_side.IT.conversion_rate
        us_win_rate = [double]($rowUS.win_rate)
        it_win_rate = [double]($rowIT.win_rate)
        us_timeout_rate = [double]($rowUS.timeout_rate)
        it_timeout_rate = [double]($rowIT.timeout_rate)
        us_tracked_captured_avg = [double]($rowUS.tracked_captured_avg)
        it_tracked_captured_avg = [double]($rowIT.tracked_captured_avg)
        elapsed_s = [double]$sw.Elapsed.TotalSeconds
      }
    }
  }

  $totalSw.Stop()
  $summaryPath = Join-Path $outDir "summary.json"
  ($rows | ConvertTo-Json -Depth 8) | Out-File -LiteralPath $summaryPath -Encoding utf8

  $aggByMode = $rows | Group-Object mode | ForEach-Object {
    $g = $_.Group
    [pscustomobject]@{
      mode = [string]$_.Name
      reps = [int]$g.Count
      objective_conversion_rate_mean = [double](($g | Measure-Object -Property objective_conversion_rate -Average).Average)
      objective_progress_rate_mean = [double](($g | Measure-Object -Property objective_progress_rate -Average).Average)
      objective_avg_progress_delta_mean = [double](($g | Measure-Object -Property objective_avg_progress_delta -Average).Average)
      us_win_rate_mean = [double](($g | Measure-Object -Property us_win_rate -Average).Average)
      it_win_rate_mean = [double](($g | Measure-Object -Property it_win_rate -Average).Average)
      us_timeout_rate_mean = [double](($g | Measure-Object -Property us_timeout_rate -Average).Average)
      it_timeout_rate_mean = [double](($g | Measure-Object -Property it_timeout_rate -Average).Average)
      us_tracked_captured_avg_mean = [double](($g | Measure-Object -Property us_tracked_captured_avg -Average).Average)
      it_tracked_captured_avg_mean = [double](($g | Measure-Object -Property it_tracked_captured_avg -Average).Average)
    }
  }
  $aggPath = Join-Path $outDir "summary_aggregate_by_mode.json"
  ($aggByMode | ConvertTo-Json -Depth 8) | Out-File -LiteralPath $aggPath -Encoding utf8

  $offAgg = $aggByMode | Where-Object { $_.mode -eq "off" } | Select-Object -First 1
  $onAgg = $aggByMode | Where-Object { $_.mode -eq "on" } | Select-Object -First 1
  $delta = [pscustomobject]@{
    off_reps = [int]($offAgg.reps | ForEach-Object { $_ })
    on_reps = [int]($onAgg.reps | ForEach-Object { $_ })
    objective_conversion_rate_delta_on_minus_off = [double](($onAgg.objective_conversion_rate_mean) - ($offAgg.objective_conversion_rate_mean))
    objective_progress_rate_delta_on_minus_off = [double](($onAgg.objective_progress_rate_mean) - ($offAgg.objective_progress_rate_mean))
    objective_avg_progress_delta_on_minus_off = [double](($onAgg.objective_avg_progress_delta_mean) - ($offAgg.objective_avg_progress_delta_mean))
    us_win_rate_delta_on_minus_off = [double](($onAgg.us_win_rate_mean) - ($offAgg.us_win_rate_mean))
    it_win_rate_delta_on_minus_off = [double](($onAgg.it_win_rate_mean) - ($offAgg.it_win_rate_mean))
    us_timeout_rate_delta_on_minus_off = [double](($onAgg.us_timeout_rate_mean) - ($offAgg.us_timeout_rate_mean))
    it_timeout_rate_delta_on_minus_off = [double](($onAgg.it_timeout_rate_mean) - ($offAgg.it_timeout_rate_mean))
    us_tracked_captured_avg_delta_on_minus_off = [double](($onAgg.us_tracked_captured_avg_mean) - ($offAgg.us_tracked_captured_avg_mean))
    it_tracked_captured_avg_delta_on_minus_off = [double](($onAgg.it_tracked_captured_avg_mean) - ($offAgg.it_tracked_captured_avg_mean))
  }
  $deltaPath = Join-Path $outDir "summary_delta_on_minus_off.json"
  ($delta | ConvertTo-Json -Depth 8) | Out-File -LiteralPath $deltaPath -Encoding utf8

  Write-Host ""
  Write-Host "== MuZero Objective Head AB3 Summary =="
  $rows | Format-Table mode, seed, run_id, objective_conversion_rate, objective_progress_rate, us_win_rate, us_timeout_rate, us_tracked_captured_avg, it_win_rate, it_timeout_rate, it_tracked_captured_avg, elapsed_s -AutoSize | Out-String | Write-Host
  Write-Host ""
  Write-Host "== Aggregate Means by Mode =="
  $aggByMode | Format-Table mode, reps, objective_conversion_rate_mean, objective_progress_rate_mean, objective_avg_progress_delta_mean, us_win_rate_mean, us_timeout_rate_mean, us_tracked_captured_avg_mean, it_win_rate_mean, it_timeout_rate_mean, it_tracked_captured_avg_mean -AutoSize | Out-String | Write-Host
  Write-Host ""
  Write-Host "== Delta (on - off) =="
  $delta | Format-List | Out-String | Write-Host
  Write-Host ("Summary JSON: " + $summaryPath)
  Write-Host ("Aggregate JSON: " + $aggPath)
  Write-Host ("Delta JSON: " + $deltaPath)
  Write-Host ("Total elapsed: {0:n1}s" -f $totalSw.Elapsed.TotalSeconds)
}
finally {
  Pop-Location
}
