[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(7, 13, 29),
  [string]$SeedsCsv = "",
  [int]$TrainIterations = 10,
  [int]$EpisodesPerIter = 8
)

$ErrorActionPreference = "Stop"

function Resolve-Seeds {
  param(
    [int[]]$SeedsArray,
    [string]$SeedsCsvText
  )
  if (-not [string]::IsNullOrWhiteSpace($SeedsCsvText)) {
    $parts = $SeedsCsvText.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    if (-not $parts.Count) { throw "SeedsCsv provided but empty after parsing." }
    $out = @()
    foreach ($p in $parts) {
      $v = 0
      if (-not [int]::TryParse($p, [ref]$v)) {
        throw ("Invalid seed value in SeedsCsv: " + $p)
      }
      $out += [int]$v
    }
    return ,$out
  }
  return ,$SeedsArray
}

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

function Build-TempConfig {
  param(
    [string]$BaseConfigPath,
    [string]$OutputPath,
    [int]$Seed,
    [string]$Mode,
    [int]$Iterations,
    [int]$Episodes
  )
  $lines = Get-Content -LiteralPath $BaseConfigPath
  $outLines = @()
  $inTrain = $false
  $inSelfplay = $false
  $inRewardShaping = $false
  foreach ($line in $lines) {
    if ($line -match '^\s*train:\s*$') {
      $inTrain = $true
      $inSelfplay = $false
      $inRewardShaping = $false
      $outLines += $line
      continue
    }
    if ($line -match '^\s*selfplay:\s*$') {
      $inSelfplay = $true
      $inTrain = $false
      $inRewardShaping = $false
      $outLines += $line
      continue
    }
    if ($line -match '^\s*reward_shaping:\s*$') {
      $inRewardShaping = $true
      $outLines += $line
      continue
    }
    if ($line -match '^\S' -and $line -notmatch '^\s*#') {
      $inTrain = $false
      $inSelfplay = $false
      $inRewardShaping = $false
    }

    if ($line -match '^\s*seed:\s*\d+\s*$') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}seed: {1}" -f $indent, [int]$Seed)
      continue
    }
    if ($inTrain -and $line -match '^\s*iterations:\s*\d+\s*$') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}iterations: {1}" -f $indent, [int]$Iterations)
      continue
    }
    if ($inTrain -and $line -match '^\s*episodes_per_iter:\s*\d+\s*$') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}episodes_per_iter: {1}" -f $indent, [int]$Episodes)
      continue
    }
    if ($inTrain -and $line -match '^\s*objective_loss_weight\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}objective_loss_weight: 0.15" -f $indent)
      } else {
        $outLines += ("{0}objective_loss_weight: 0.0" -f $indent)
      }
      continue
    }
    if ($inTrain -and $line -match '^\s*objective_target_mode\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      $outLines += ("{0}objective_target_mode: progress" -f $indent)
      continue
    }
    if ($inTrain -and $line -match '^\s*objective_pos_weight\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}objective_pos_weight: 6.0" -f $indent)
      } else {
        $outLines += ("{0}objective_pos_weight: 4.0" -f $indent)
      }
      continue
    }
    if ($inSelfplay -and -not $inRewardShaping -and $line -match '^\s*timeout_penalty\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}timeout_penalty: -0.38" -f $indent)
      } else {
        $outLines += ("{0}timeout_penalty: -0.30" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*vp_capture_bonus_per_hex\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}vp_capture_bonus_per_hex: 0.75" -f $indent)
      } else {
        $outLines += ("{0}vp_capture_bonus_per_hex: 0.55" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*vp_net_gain_bonus\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}vp_net_gain_bonus: 0.20" -f $indent)
      } else {
        $outLines += ("{0}vp_net_gain_bonus: 0.12" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*objective_progress_bonus_per_hex\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}objective_progress_bonus_per_hex: 0.36" -f $indent)
      } else {
        $outLines += ("{0}objective_progress_bonus_per_hex: 0.00" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*objective_no_progress_penalty\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}objective_no_progress_penalty: 0.16" -f $indent)
      } else {
        $outLines += ("{0}objective_no_progress_penalty: 0.00" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*objective_no_progress_attack_penalty\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}objective_no_progress_attack_penalty: 0.24" -f $indent)
      } else {
        $outLines += ("{0}objective_no_progress_attack_penalty: 0.00" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*idle_penalty\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}idle_penalty: -0.07" -f $indent)
      } else {
        $outLines += ("{0}idle_penalty: -0.03" -f $indent)
      }
      continue
    }
    if ($inRewardShaping -and $line -match '^\s*idle_with_options_multiplier\s*:') {
      $indent = ([regex]::Match($line, '^\s*')).Value
      if ($Mode -eq "progress") {
        $outLines += ("{0}idle_with_options_multiplier: 3.0" -f $indent)
      } else {
        $outLines += ("{0}idle_with_options_multiplier: 2.0" -f $indent)
      }
      continue
    }
    $outLines += $line
  }
  Set-Content -LiteralPath $OutputPath -Value ($outLines -join "`r`n") -Encoding utf8
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $resolvedSeeds = Resolve-Seeds -SeedsArray $Seeds -SeedsCsvText $SeedsCsv
  if (-not $resolvedSeeds -or $resolvedSeeds.Count -le 0) {
    throw "No seeds resolved."
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $outDir = Join-Path $Repo ("runs\vp_progress_ab3\" + $stamp)
  New-Item -ItemType Directory -Path $outDir -Force | Out-Null

  $baseTrainCfg = Join-Path $Repo "agents/muzero/configs/muzero_config.smoke.yaml"
  $baseBenchCfg = Join-Path $Repo "assault_bench/configs/benchmark_config.smoke.yaml"
  if (-not (Test-Path -LiteralPath $baseTrainCfg)) { throw "Missing $baseTrainCfg" }
  if (-not (Test-Path -LiteralPath $baseBenchCfg)) { throw "Missing $baseBenchCfg" }

  $rows = @()
  $totalSw = [System.Diagnostics.Stopwatch]::StartNew()

  foreach ($seed in $resolvedSeeds) {
    foreach ($mode in @("baseline", "progress")) {
      Write-Host ""
      Write-Host ("== VP Progress AB3 | mode={0} seed={1} iter={2} epi={3} ==" -f $mode, $seed, $TrainIterations, $EpisodesPerIter)
      $beforeRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
      $tmpTrainCfg = Join-Path $outDir ("muzero_config." + $mode + ".seed_" + $seed + ".yaml")
      Build-TempConfig `
        -BaseConfigPath $baseTrainCfg `
        -OutputPath $tmpTrainCfg `
        -Seed ([int]$seed) `
        -Mode ([string]$mode) `
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
        throw ("run_muzero_train_and_bench failed for mode={0} seed={1} exit={2}" -f $mode, $seed, $LASTEXITCODE)
      }
      $sw.Stop()

      $afterRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
      if ([string]::IsNullOrWhiteSpace($afterRunId) -or $afterRunId -eq $beforeRunId) {
        throw ("Could not detect new MuZero run_id for mode={0} seed={1}" -f $mode, $seed)
      }

      $benchPath = Join-Path $Repo "runs\bench_latest.json"
      $benchCopy = Join-Path $outDir ("bench_" + $mode + "_seed_" + $seed + ".json")
      Copy-Item -LiteralPath $benchPath -Destination $benchCopy -Force
      $benchJson = Get-Content -LiteralPath $benchCopy -Raw | ConvertFrom-Json
      $rowUS = Get-BenchRow -BenchJson $benchJson -AgentName "muzero_vs_random_US"
      $rowIT = Get-BenchRow -BenchJson $benchJson -AgentName "muzero_vs_random_IT"

      $unitsSidesPath = Join-Path $Repo ("runs\" + $afterRunId + "\metrics\units_sides.json")
      $unitsJson = Get-Content -LiteralPath $unitsSidesPath -Raw | ConvertFrom-Json
      $opf = $unitsJson.diagnostics_summary.objective_progress_funnel
      $opx = $unitsJson.diagnostics_summary.objective_progress_explain
      $nprUS = 0.0
      $nprIT = 0.0
      if ($null -ne $opx -and $null -ne $opx.by_side) {
        if ($null -ne $opx.by_side.US -and $null -ne $opx.by_side.US.no_progress_reason_counts) {
          $vUS = $opx.by_side.US.no_progress_reason_counts.attack_or_capture_without_progress
          if ($null -ne $vUS) { $nprUS = [double]$vUS }
        }
        if ($null -ne $opx.by_side.IT -and $null -ne $opx.by_side.IT.no_progress_reason_counts) {
          $vIT = $opx.by_side.IT.no_progress_reason_counts.attack_or_capture_without_progress
          if ($null -ne $vIT) { $nprIT = [double]$vIT }
        }
      }

      $rows += [pscustomobject]@{
        mode = [string]$mode
        seed = [int]$seed
        run_id = [string]$afterRunId
        objective_progress_rate = [double]$opf.global.progress_rate
        objective_conversion_rate = [double]$opf.global.conversion_rate
        objective_avg_progress_delta = [double]$opf.global.avg_progress_delta
        objective_opportunities = [int]$opf.global.opportunities
        no_progress_attack_us = [double]$nprUS
        no_progress_attack_it = [double]$nprIT
        us_win_rate = [double]($rowUS.win_rate)
        it_win_rate = [double]($rowIT.win_rate)
        us_turn_limit_finish_rate = [double]($rowUS.timeout_rate)
        it_turn_limit_finish_rate = [double]($rowIT.timeout_rate)
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
      objective_progress_rate_mean = [double](($g | Measure-Object -Property objective_progress_rate -Average).Average)
      objective_conversion_rate_mean = [double](($g | Measure-Object -Property objective_conversion_rate -Average).Average)
      objective_avg_progress_delta_mean = [double](($g | Measure-Object -Property objective_avg_progress_delta -Average).Average)
      no_progress_attack_us_mean = [double](($g | Measure-Object -Property no_progress_attack_us -Average).Average)
      no_progress_attack_it_mean = [double](($g | Measure-Object -Property no_progress_attack_it -Average).Average)
      us_win_rate_mean = [double](($g | Measure-Object -Property us_win_rate -Average).Average)
      it_win_rate_mean = [double](($g | Measure-Object -Property it_win_rate -Average).Average)
      us_turn_limit_finish_rate_mean = [double](($g | Measure-Object -Property us_turn_limit_finish_rate -Average).Average)
      it_turn_limit_finish_rate_mean = [double](($g | Measure-Object -Property it_turn_limit_finish_rate -Average).Average)
      us_tracked_captured_avg_mean = [double](($g | Measure-Object -Property us_tracked_captured_avg -Average).Average)
      it_tracked_captured_avg_mean = [double](($g | Measure-Object -Property it_tracked_captured_avg -Average).Average)
    }
  }
  $aggPath = Join-Path $outDir "summary_aggregate_by_mode.json"
  ($aggByMode | ConvertTo-Json -Depth 8) | Out-File -LiteralPath $aggPath -Encoding utf8

  $base = $aggByMode | Where-Object { $_.mode -eq "baseline" } | Select-Object -First 1
  $prog = $aggByMode | Where-Object { $_.mode -eq "progress" } | Select-Object -First 1
  $delta = [pscustomobject]@{
    baseline_reps = [int]($base.reps | ForEach-Object { $_ })
    progress_reps = [int]($prog.reps | ForEach-Object { $_ })
    objective_progress_rate_delta_progress_minus_baseline = [double](($prog.objective_progress_rate_mean) - ($base.objective_progress_rate_mean))
    objective_conversion_rate_delta_progress_minus_baseline = [double](($prog.objective_conversion_rate_mean) - ($base.objective_conversion_rate_mean))
    objective_avg_progress_delta_progress_minus_baseline = [double](($prog.objective_avg_progress_delta_mean) - ($base.objective_avg_progress_delta_mean))
    no_progress_attack_us_delta_progress_minus_baseline = [double](($prog.no_progress_attack_us_mean) - ($base.no_progress_attack_us_mean))
    no_progress_attack_it_delta_progress_minus_baseline = [double](($prog.no_progress_attack_it_mean) - ($base.no_progress_attack_it_mean))
    us_win_rate_delta_progress_minus_baseline = [double](($prog.us_win_rate_mean) - ($base.us_win_rate_mean))
    it_win_rate_delta_progress_minus_baseline = [double](($prog.it_win_rate_mean) - ($base.it_win_rate_mean))
    us_turn_limit_finish_rate_delta_progress_minus_baseline = [double](($prog.us_turn_limit_finish_rate_mean) - ($base.us_turn_limit_finish_rate_mean))
    it_turn_limit_finish_rate_delta_progress_minus_baseline = [double](($prog.it_turn_limit_finish_rate_mean) - ($base.it_turn_limit_finish_rate_mean))
    us_tracked_captured_avg_delta_progress_minus_baseline = [double](($prog.us_tracked_captured_avg_mean) - ($base.us_tracked_captured_avg_mean))
    it_tracked_captured_avg_delta_progress_minus_baseline = [double](($prog.it_tracked_captured_avg_mean) - ($base.it_tracked_captured_avg_mean))
  }
  $deltaPath = Join-Path $outDir "summary_delta_progress_minus_baseline.json"
  ($delta | ConvertTo-Json -Depth 8) | Out-File -LiteralPath $deltaPath -Encoding utf8

  Write-Host ""
  Write-Host "== MuZero VP Progress AB3 Summary =="
  $rows | Format-Table mode, seed, run_id, objective_progress_rate, objective_conversion_rate, no_progress_attack_us, no_progress_attack_it, us_win_rate, us_turn_limit_finish_rate, us_tracked_captured_avg, elapsed_s -AutoSize | Out-String | Write-Host
  Write-Host ""
  Write-Host "== Aggregate Means by Mode =="
  $aggByMode | Format-Table mode, reps, objective_progress_rate_mean, objective_conversion_rate_mean, no_progress_attack_us_mean, no_progress_attack_it_mean, us_win_rate_mean, us_turn_limit_finish_rate_mean, us_tracked_captured_avg_mean -AutoSize | Out-String | Write-Host
  Write-Host ""
  Write-Host "== Delta (progress - baseline) =="
  $delta | Format-List | Out-String | Write-Host
  Write-Host ("Summary JSON: " + $summaryPath)
  Write-Host ("Aggregate JSON: " + $aggPath)
  Write-Host ("Delta JSON: " + $deltaPath)
  Write-Host ("Total elapsed: {0:n1}s" -f $totalSw.Elapsed.TotalSeconds)
}
finally {
  Pop-Location
}
