param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$CurriculumYaml = ".\curriculums\self_vs_self_vs_random_v1\curriculum.yaml",
  [string]$StartPhase = "",
  [switch]$ContinueFromLatestCheckpoint,
  [switch]$StrictPhaseResume,
  [switch]$AllowPhase1Resume,
  [switch]$StopOnGateFail,
  [switch]$StopOnPhaseError,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function ConvertTo-CompactJson {
  param($Value)
  return ($Value | ConvertTo-Json -Depth 64 -Compress)
}

function Get-Sha1Hex12 {
  param([string]$Text)
  if ([string]::IsNullOrEmpty($Text)) { return "" }
  $sha = [System.Security.Cryptography.SHA1]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hash = $sha.ComputeHash($bytes)
    $hex = -join ($hash | ForEach-Object { $_.ToString("x2") })
    if ($hex.Length -gt 12) { return $hex.Substring(0, 12) }
    return $hex
  } finally {
    $sha.Dispose()
  }
}

function Resolve-CommandArgValue {
  param(
    [string]$Command,
    [string]$ArgName
  )
  if ([string]::IsNullOrWhiteSpace($Command) -or [string]::IsNullOrWhiteSpace($ArgName)) {
    return ""
  }
  $pat = [regex]::Escape($ArgName) + "\s+(""(?<val>[^""]+)""|(?<val>\S+))"
  $m = [regex]::Match($Command, $pat)
  if (-not $m.Success) { return "" }
  return [string]$m.Groups["val"].Value
}

function Get-YamlObject {
  param([string]$YamlPath)
  if ([string]::IsNullOrWhiteSpace($YamlPath) -or -not (Test-Path $YamlPath)) { return $null }
  $py = @"
import json, pathlib, yaml
p = pathlib.Path(r'''$YamlPath''').resolve()
obj = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
print(json.dumps(obj))
"@
  $raw = python -c $py
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
  return ($raw | ConvertFrom-Json)
}

function Resolve-RunIdFromPath {
  param([string]$PathText)
  $raw = [string]$PathText
  if ([string]::IsNullOrWhiteSpace($raw)) { return "" }
  $norm = $raw.Replace("\", "/")
  $parts = @($norm.Split("/") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  if ($parts.Count -eq 0) { return "" }
  for ($i = 0; $i -lt $parts.Count; $i++) {
    if ($parts[$i] -eq "checkpoints" -and $i -gt 0) { return [string]$parts[$i - 1] }
  }
  foreach ($p in $parts) {
    if ($p.StartsWith("efficientzero_v2_") -or $p.StartsWith("muzero_")) { return [string]$p }
  }
  return ""
}

function Write-CurriculumTraceRow {
  param(
    [string]$RepoRoot,
    [hashtable]$Row
  )
  $traceDir = Join-Path $RepoRoot "runs_curriculum\experiments\reporting"
  New-Item -ItemType Directory -Path $traceDir -Force | Out-Null
  $jsonlPath = Join-Path $traceDir "curriculum_phase_traceability.jsonl"
  $latestPath = Join-Path $traceDir "curriculum_phase_traceability.latest.json"
  Add-Content -Path $jsonlPath -Value (ConvertTo-CompactJson $Row) -Encoding UTF8
  ($Row | ConvertTo-Json -Depth 64) | Set-Content -Path $latestPath -Encoding UTF8
}

function Get-CurriculumJson {
  param([string]$YamlPath)
  $py = @"
import json, yaml, pathlib
p = pathlib.Path(r'''$YamlPath''').resolve()
obj = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
print(json.dumps(obj))
"@
  $raw = python -c $py
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
    throw "Failed to parse curriculum yaml: $YamlPath"
  }
  return ($raw | ConvertFrom-Json)
}

function Get-MainRow {
  param($BenchPayload)
  $rows = @($BenchPayload.results)
  $main = $rows | Where-Object {
    $n = [string]($_.agent_name)
    $n -in @("efficientzero_v2_stub", "muzero_stub")
  } | Select-Object -First 1
  if ($null -eq $main) {
    $main = $rows | Select-Object -First 1
  }
  return $main
}

function Evaluate-Gate {
  param(
    $BenchPayload,
    $GateSpec,
    $PrevMetrics,
    [string[]]$ExpectedScenarioIds = @()
  )
  $reasons = New-Object System.Collections.Generic.List[string]
  $ok = $true

  $promo = @{}
  if ($BenchPayload.phase_2_9_promotion_gate) { $promo = $BenchPayload.phase_2_9_promotion_gate }
  $promoStatus = [string]($promo.status)
  if ($promoStatus -and $promoStatus -ne "PASS") {
    $ok = $false
    $reasons.Add("phase_2_9_promotion_gate.status=$promoStatus")
  }

  $rows = @($BenchPayload.results)
  if (-not $rows -or $rows.Count -eq 0) {
    return @{
      ok = $false
      reasons = @("missing results row in bench payload")
      metrics = @{}
    }
  }

  $expectedScenarioIdsNorm = @(
    @($ExpectedScenarioIds) |
      ForEach-Object { [string]$_ } |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
      Sort-Object -Unique
  )
  if ($expectedScenarioIdsNorm.Count -gt 1) {
    $seenScenarioIds = New-Object System.Collections.Generic.HashSet[string]
    foreach ($rr in $rows) {
      $seedGames = @($rr.seed_games)
      foreach ($sg in $seedGames) {
        $sid = [string]$sg.scenario_id
        if (-not [string]::IsNullOrWhiteSpace($sid)) {
          [void]$seenScenarioIds.Add($sid)
        }
      }
    }
    $missingScenarioIds = @()
    foreach ($sidExpected in $expectedScenarioIdsNorm) {
      if (-not $seenScenarioIds.Contains([string]$sidExpected)) {
        $missingScenarioIds += [string]$sidExpected
      }
    }
    if ($missingScenarioIds.Count -gt 0) {
      $ok = $false
      $reasons.Add(
        "scenario coverage fail: expected scenario_ids [" +
        (($expectedScenarioIdsNorm -join ", ")) +
        "] but missing [" + (($missingScenarioIds -join ", ")) + "]"
      )
    }
  }

  # Global gate uses all MCTS-driven profiles (selfplay + vs_random),
  # weighted by episodes, so promotion is not biased to one profile.
  $mctsRows = @(
    $rows | Where-Object {
      [string]::Equals([string]$_.policy_name, "mcts", [System.StringComparison]::OrdinalIgnoreCase)
    }
  )
  if (-not $mctsRows -or $mctsRows.Count -eq 0) {
    $mctsRows = $rows
  }
  $main = $mctsRows | Select-Object -First 1
  $totEpisodes = [double]0.0
  $sumScore = [double]0.0
  $sumTimeout = [double]0.0
  $sumLoss = [double]0.0
  $sumVpCapture = [double]0.0
  $sumTrackedCaptured = [double]0.0
  $sumVpNetTracked = [double]0.0
  $profileScoreMap = @{}
  $profileLossRateMap = @{}
  foreach ($rowProfile in $mctsRows) {
    $pn = [string]($rowProfile.matchup_profile)
    if (-not [string]::IsNullOrWhiteSpace($pn)) {
      $profileScoreMap[$pn] = [double]($rowProfile.win_rate)
      $profileLossRateMap[$pn] = [double]($rowProfile.loss_rate)
    }
  }
  foreach ($r in $mctsRows) {
    $eps = [double]([math]::Max(1, [int]($r.episodes)))
    $totEpisodes += $eps
    $sumScore += $eps * [double]($r.win_rate)
    $sumTimeout += $eps * [double]($r.timeout_rate)
    $sumLoss += $eps * [double]($r.loss_rate)
    $sumTrackedCaptured += $eps * [double]($r.tracked_captured_avg)
    $rowTrackedSide = [string]($r.tracked_side)
    $rowVpNet = [double]0.0
    if ($r.vp_net_avg_by_side -and $rowTrackedSide) {
      $vpNetProp = $r.vp_net_avg_by_side.PSObject.Properties[$rowTrackedSide]
      if ($vpNetProp -ne $null -and $vpNetProp.Value -ne $null) {
        $rowVpNet = [double]$vpNetProp.Value
      }
    }
    $sumVpNetTracked += $eps * $rowVpNet
    $rowKpis = @{}
    if ($r.phase_2_9_eval_kpis) { $rowKpis = $r.phase_2_9_eval_kpis }
    $sumVpCapture += $eps * [double]($rowKpis.xai_vp_capture_take_rate)
  }
  $den = [double]([math]::Max(1.0, $totEpisodes))
  $score = $sumScore / $den
  $timeoutRate = $sumTimeout / $den
  $nonTimeoutResolutionRate = 1.0 - $timeoutRate
  if ($main.PSObject.Properties.Name -contains "non_timeout_resolution_rate" -and $main.non_timeout_resolution_rate -ne $null) {
    $nonTimeoutResolutionRate = [double]($main.non_timeout_resolution_rate)
  }
  $resolvedNonTimeoutWinRate = $score
  if ($main.PSObject.Properties.Name -contains "resolved_non_timeout_win_rate" -and $main.resolved_non_timeout_win_rate -ne $null) {
    $resolvedNonTimeoutWinRate = [double]($main.resolved_non_timeout_win_rate)
  } elseif ($main.seed_games) {
    $seedRows = @($main.seed_games)
    $resolvedRows = @($seedRows | Where-Object { -not [bool]$_.timeout })
    if ($resolvedRows.Count -gt 0) {
      $resolvedWins = @(
        $resolvedRows | Where-Object {
          $w = $_.winner_side
          if ([string]::IsNullOrWhiteSpace([string]$w)) { return $false }
          $ctrl = $_.controller_by_side
          if ($null -eq $ctrl) { return $false }
          $ctrlVal = [string]$ctrl.$w
          return ($ctrlVal -eq "MuZero")
        }
      ).Count
      $resolvedNonTimeoutWinRate = [double]$resolvedWins / [double]$resolvedRows.Count
    } else {
      $resolvedNonTimeoutWinRate = 0.0
    }
  }
  $lossRate = $sumLoss / $den
  $trackedCapturedAvg = $sumTrackedCaptured / $den
  $trackedSide = [string]($main.tracked_side)
  $vpNetTrackedSide = $sumVpNetTracked / $den
  $vpCaptureTakeRate = $sumVpCapture / $den

  # Optional strict per-profile guardrails (if provided in gate YAML):
  # profile_min_score:
  #   muzero_selfplay: 0.58
  #   muzero_vs_random_side_a: 0.92
  if ($GateSpec.profile_min_score) {
    foreach ($profileProp in $GateSpec.profile_min_score.PSObject.Properties) {
      $profileName = [string]$profileProp.Name
      $thScore = [double]$profileProp.Value
      $pr = $mctsRows | Where-Object { [string]$_.matchup_profile -eq $profileName } | Select-Object -First 1
      if ($null -eq $pr) {
        $ok = $false
        $reasons.Add("profile '$profileName' missing in benchmark results")
        continue
      }
      $profileScore = [double]($pr.win_rate)
      if ($profileScore -lt $thScore) {
        $ok = $false
        $reasons.Add("profile '$profileName' score $profileScore < min $thScore")
      }
    }
  }

  # Optional soft guardrails by profile while keeping promotion decision global.
  # Example:
  # profile_soft_guardrail:
  #   muzero_vs_random_side_b:
  #     severe_min_score: 0.03
  #     max_score_drop_vs_prev: 0.20
  if ($GateSpec.profile_soft_guardrail) {
    foreach ($guardProp in $GateSpec.profile_soft_guardrail.PSObject.Properties) {
      $profileName = [string]$guardProp.Name
      $guardSpec = $guardProp.Value
      $pr = $mctsRows | Where-Object { [string]$_.matchup_profile -eq $profileName } | Select-Object -First 1
      if ($null -eq $pr) { continue }
      $profileScore = [double]($pr.win_rate)
      if ($guardSpec.severe_min_score -ne $null) {
        $thSevere = [double]$guardSpec.severe_min_score
        if ($profileScore -lt $thSevere) {
          $ok = $false
          $reasons.Add("profile '$profileName' severe floor: score $profileScore < severe_min_score $thSevere")
        }
      }
      if ($guardSpec.max_score_drop_vs_prev -ne $null -and $PrevMetrics -and $PrevMetrics.profile_scores) {
        $prevProp = $PrevMetrics.profile_scores.PSObject.Properties[$profileName]
        if ($prevProp -ne $null -and $prevProp.Value -ne $null) {
          $prevScore = [double]$prevProp.Value
          $maxDrop = [double]$guardSpec.max_score_drop_vs_prev
          $drop = [double]$prevScore - [double]$profileScore
          if ($drop -gt $maxDrop) {
            $ok = $false
            $reasons.Add("profile '$profileName' score drop $drop > max_score_drop_vs_prev $maxDrop")
          }
        }
      }
    }
  }

  if ($GateSpec.min_score -ne $null) {
    $th = [double]$GateSpec.min_score
    if ($score -lt $th) {
      $ok = $false
      $reasons.Add("score $score < min_score $th")
    }
  }
  # Timeout-related metrics are diagnostic only for this game mode and must not
  # block curriculum promotion gates. Keep them in metrics/logs for observability.
  if ($GateSpec.min_vp_capture_take_rate -ne $null) {
    $th = [double]$GateSpec.min_vp_capture_take_rate
    if ($vpCaptureTakeRate -lt $th) {
      $ok = $false
      $reasons.Add("xai_vp_capture_take_rate $vpCaptureTakeRate < min_vp_capture_take_rate $th")
    }
  }
  if ($GateSpec.min_tracked_captured_avg -ne $null) {
    $th = [double]$GateSpec.min_tracked_captured_avg
    if ($trackedCapturedAvg -lt $th) {
      $ok = $false
      $reasons.Add("tracked_captured_avg $trackedCapturedAvg < min_tracked_captured_avg $th")
    }
  }
  if ($GateSpec.min_vp_net_avg_tracked_side -ne $null) {
    $th = [double]$GateSpec.min_vp_net_avg_tracked_side
    if ($vpNetTrackedSide -lt $th) {
      $ok = $false
      $reasons.Add("vp_net_avg_tracked_side $vpNetTrackedSide < min_vp_net_avg_tracked_side $th")
    }
  }
  if ($GateSpec.no_regression_defeat_rate -eq $true -and $PrevMetrics) {
    $prevLoss = [double]$PrevMetrics.loss_rate
    if ($lossRate -gt $prevLoss) {
      $ok = $false
      $reasons.Add("loss_rate regression: $lossRate > previous $prevLoss")
    }
  }
  if ($GateSpec.min_vp_capture_take_rate_delta -ne $null -and $PrevMetrics) {
    $th = [double]$GateSpec.min_vp_capture_take_rate_delta
    $delta = [double]$vpCaptureTakeRate - [double]$PrevMetrics.vp_capture_take_rate
    if ($delta -lt $th) {
      $ok = $false
      $reasons.Add("vp_capture_take_rate delta $delta < min_vp_capture_take_rate_delta $th")
    }
  }

  return @{
    ok = $ok
    reasons = @($reasons)
    metrics = @{
      score = $score
      timeout_rate = $timeoutRate
      non_timeout_resolution_rate = $nonTimeoutResolutionRate
      resolved_non_timeout_win_rate = $resolvedNonTimeoutWinRate
      loss_rate = $lossRate
      vp_capture_take_rate = $vpCaptureTakeRate
      tracked_captured_avg = $trackedCapturedAvg
      tracked_side = $trackedSide
      vp_net_avg_tracked_side = $vpNetTrackedSide
      profile_scores = $profileScoreMap
      profile_loss_rates = $profileLossRateMap
    }
  }
}

function Resolve-BenchLatestPath {
  param(
    [string]$RepoRoot,
    [string]$RunsRootPreferred
  )
  $candidates = @()
  if (-not [string]::IsNullOrWhiteSpace($RunsRootPreferred)) {
    $candidates += (Join-Path $RepoRoot (Join-Path $RunsRootPreferred "bench_latest.json"))
  }
  $candidates += (Join-Path $RepoRoot "runs_curriculum\bench_latest.json")
  $candidates += (Join-Path $RepoRoot "runs\bench_latest.json")
  foreach ($p in $candidates) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

function Resolve-BenchPayloadPath {
  param(
    [string]$RepoRoot,
    [string]$RunsRootPreferred,
    [string]$PhaseName,
    [datetime]$NotBeforeUtc
  )
  function Test-BenchPayloadHasResults {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path $Path)) { return $false }
    try {
      $payload = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json
      $rows = @($payload.results)
      return ($rows.Count -gt 0)
    } catch {
      return $false
    }
  }

  $latest = Resolve-BenchLatestPath -RepoRoot $RepoRoot -RunsRootPreferred $RunsRootPreferred
  if (-not [string]::IsNullOrWhiteSpace([string]$latest) -and (Test-Path $latest)) {
    $latestItem = Get-Item $latest
    $isRecentEnough = ($latestItem.LastWriteTimeUtc -ge $NotBeforeUtc)
    if ($isRecentEnough -and (Test-BenchPayloadHasResults -Path $latest)) {
      return [string]$latest
    }
  }
  $roots = @()
  if (-not [string]::IsNullOrWhiteSpace($RunsRootPreferred)) {
    $roots += (Join-Path $RepoRoot $RunsRootPreferred)
  }
  $roots += (Join-Path $RepoRoot "runs_curriculum")
  $roots += (Join-Path $RepoRoot "runs")
  $candidates = @()
  foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    $candidates += Get-ChildItem -Path $root -Recurse -File -Filter "bench_eval_*.json" -ErrorAction SilentlyContinue
  }
  if (-not $candidates -or $candidates.Count -eq 0) { return $null }
  $fresh = @($candidates | Where-Object { $_.LastWriteTimeUtc -ge $NotBeforeUtc })
  if ($fresh.Count -gt 0) { $candidates = $fresh }
  $phaseNorm = [string]$PhaseName
  $phaseScoped = @(
    $candidates | Where-Object {
      $_.FullName -match [regex]::Escape($phaseNorm) -or $_.DirectoryName -match [regex]::Escape($phaseNorm)
    }
  )
  $pool = $phaseScoped
  if (-not $pool -or $pool.Count -eq 0) { $pool = $candidates }
  $ordered = @($pool | Sort-Object LastWriteTimeUtc -Descending)
  foreach ($item in $ordered) {
    if (Test-BenchPayloadHasResults -Path $item.FullName) {
      return [string]$item.FullName
    }
  }
  return $null
}

function Resolve-LatestCheckpointPath {
  param(
    [string]$RepoRoot,
    [string]$RunsRootPreferred
  )
  $roots = @()
  if (-not [string]::IsNullOrWhiteSpace($RunsRootPreferred)) {
    $roots += (Join-Path $RepoRoot $RunsRootPreferred)
  }
  $roots += (Join-Path $RepoRoot "runs_curriculum")
  $roots += (Join-Path $RepoRoot "runs")
  $candidates = @()
  foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    $finals = Get-ChildItem -Path $root -Recurse -File -Filter "final.pt" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "(efficientzero_v2_|muzero_).+\\checkpoints\\final\.pt$" }
    $iters = Get-ChildItem -Path $root -Recurse -File -Filter "iter_*.pt" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "(efficientzero_v2_|muzero_).+\\checkpoints\\iter_\d+\.pt$" }
    $candidates += @($finals)
    $candidates += @($iters)
  }
  if (-not $candidates -or $candidates.Count -eq 0) { return $null }
  $latest = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  return [string]$latest.FullName
}

function Resolve-LatestCheckpointPathSince {
  param(
    [string]$RepoRoot,
    [string]$RunsRootPreferred,
    [datetime]$NotBeforeUtc
  )
  $roots = @()
  if (-not [string]::IsNullOrWhiteSpace($RunsRootPreferred)) {
    $roots += (Join-Path $RepoRoot $RunsRootPreferred)
  }
  $roots += (Join-Path $RepoRoot "runs_curriculum")
  $roots += (Join-Path $RepoRoot "runs")
  $candidates = @()
  foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    $finals = Get-ChildItem -Path $root -Recurse -File -Filter "final.pt" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "(efficientzero_v2_|muzero_).+\\checkpoints\\final\.pt$" }
    $iters = Get-ChildItem -Path $root -Recurse -File -Filter "iter_*.pt" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "(efficientzero_v2_|muzero_).+\\checkpoints\\iter_\d+\.pt$" }
    $candidates += @($finals)
    $candidates += @($iters)
  }
  if (-not $candidates -or $candidates.Count -eq 0) { return $null }
  $fresh = @($candidates | Where-Object { $_.LastWriteTimeUtc -ge $NotBeforeUtc })
  if ($fresh.Count -gt 0) {
    $latestFresh = $fresh | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    return [string]$latestFresh.FullName
  }
  return $null
}

function Resolve-CheckpointFromCycleTrainLog {
  param(
    [string]$RepoRoot,
    [string]$CurriculumName,
    [string]$PhaseName
  )
  if ([string]::IsNullOrWhiteSpace($CurriculumName) -or [string]::IsNullOrWhiteSpace($PhaseName)) {
    return $null
  }
  $cyclesRoot = Join-Path $RepoRoot "runs_curriculum\experiments\curriculum_cycles"
  if (-not (Test-Path $cyclesRoot)) { return $null }
  $needle = ("_" + [string]$CurriculumName + "_" + [string]$PhaseName)
  $dirs = @(
    Get-ChildItem -Path $cyclesRoot -Directory -ErrorAction SilentlyContinue |
      Where-Object { [string]$_.Name -like ("*" + $needle) } |
      Sort-Object LastWriteTimeUtc -Descending
  )
  foreach ($d in $dirs) {
    $trainLog = Join-Path $d.FullName "logs\01_train.log"
    if (-not (Test-Path $trainLog)) { continue }
    try {
      $raw = Get-Content -Path $trainLog -Raw -Encoding UTF8
      $mFinal = [regex]::Matches($raw, "final_checkpoint=(?<ckpt>[^\r\n]+)")
      if ($mFinal.Count -gt 0) {
        $ckptRaw = [string]$mFinal[$mFinal.Count - 1].Groups["ckpt"].Value
        $ckpt = $ckptRaw.Trim().Replace("/", "\")
        if (-not [System.IO.Path]::IsPathRooted($ckpt)) {
          $ckpt = Join-Path $RepoRoot $ckpt
        }
        if (Test-Path $ckpt) { return [string]$ckpt }
      }
      $mIter = [regex]::Matches($raw, "checkpoint=(?<ckpt>[^\r\n]+)")
      if ($mIter.Count -gt 0) {
        $ckptRaw = [string]$mIter[$mIter.Count - 1].Groups["ckpt"].Value
        $ckpt = $ckptRaw.Trim().Replace("/", "\")
        if (-not [System.IO.Path]::IsPathRooted($ckpt)) {
          $ckpt = Join-Path $RepoRoot $ckpt
        }
        if (Test-Path $ckpt) { return [string]$ckpt }
      }
    } catch {
      continue
    }
  }
  return $null
}

function Set-TrainConfigInCommand {
  param(
    [string]$TrainCommand,
    [string]$NewConfigPath
  )
  $newCfg = [string]$NewConfigPath
  $quoted = '"' + $newCfg + '"'
  $pattern = "--config\s+(""[^""]+""|\S+)"
  if ([regex]::IsMatch($TrainCommand, $pattern)) {
    return [regex]::Replace($TrainCommand, $pattern, "--config $quoted", 1)
  }
  return ($TrainCommand + " --config " + $quoted)
}

function Build-ResumeOverlayConfig {
  param(
    [string]$RepoRoot,
    [string]$BaseConfigPath,
    [string]$ResumeCheckpoint,
    [string]$PhaseName
  )
  $outDir = Join-Path $RepoRoot "runs_curriculum\experiments\curriculum_runtime_configs"
  New-Item -ItemType Directory -Path $outDir -Force | Out-Null
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $safePhase = ($PhaseName -replace "[^a-zA-Z0-9._-]", "_")
  $outPath = Join-Path $outDir ("resume_overlay_{0}_{1}.yaml" -f $safePhase, $stamp)
  $baseNorm = [string]$BaseConfigPath -replace "\\","/"
  $resumeNorm = [string]$ResumeCheckpoint -replace "\\","/"
  $content = @(
    ("base_config: " + $baseNorm),
    "",
    "train:",
    ("  resume_checkpoint: """ + $resumeNorm + """")
  ) -join "`r`n"
  Set-Content -Path $outPath -Value $content -Encoding UTF8
  return $outPath
}

Push-Location $Repo
try {
  $curr = Get-CurriculumJson -YamlPath $CurriculumYaml
  $curriculumPathResolved = (Resolve-Path $CurriculumYaml).Path
  $curriculumName = [string]$curr.name
  if ([string]::IsNullOrWhiteSpace($curriculumName)) {
    $curriculumName = [System.IO.Path]::GetFileNameWithoutExtension($curriculumPathResolved)
  }
  $curriculumRaw = Get-Content -Path $curriculumPathResolved -Raw -Encoding UTF8
  $curriculumVersion = Get-Sha1Hex12 -Text $curriculumRaw
  $currDir = Split-Path -Parent (Resolve-Path $CurriculumYaml).Path
  $phases = @($curr.phases)
  if (-not $phases.Count) { throw "No phases found in curriculum: $CurriculumYaml" }
  $firstPhaseName = [string]$phases[0].name
  $startPhaseNorm = [string]$StartPhase
  $started = [string]::IsNullOrWhiteSpace($startPhaseNorm)
  if (-not $started) {
    $exists = $false
    foreach ($p in $phases) {
      if ([string]$p.name -eq $startPhaseNorm) { $exists = $true; break }
    }
    if (-not $exists) {
      throw "StartPhase '$startPhaseNorm' not found in curriculum."
    }
  }

  $prevMetrics = $null
  $resumeCheckpoint = $null
  $gateFailures = New-Object System.Collections.Generic.List[object]
  $phaseFailures = New-Object System.Collections.Generic.List[object]
  for ($phaseIdx = 0; $phaseIdx -lt $phases.Count; $phaseIdx++) {
    $phase = $phases[$phaseIdx]
    $phaseName = [string]$phase.name
    $prevPhaseName = ""
    if ($phaseIdx -gt 0) {
      $prevPhaseName = [string]$phases[$phaseIdx - 1].name
    }
    $phaseStartUtc = (Get-Date).ToUniversalTime()
    $phaseEndUtc = $null
    $phaseGateResult = "UNKNOWN"
    $phaseGateReasons = @()
    $promotionDecision = "hold"
    $promotionReason = ""
    $currentGateMetrics = @{}
    $benchLatest = ""
    $bench = $null
    $evalRunId = ""
    $trainRunId = ""
    $checkpointPathUsed = [string]$resumeCheckpoint
    $manifestObj = $null
    if (-not $started) {
      if ($phaseName -ne $startPhaseNorm) { continue }
      $started = $true
      Write-Host "Resuming from phase: $phaseName"
    }
    try {
      $manifest = Join-Path $currDir ("cycles\" + $phaseName + ".cycle.json")
      if (-not (Test-Path $manifest)) {
        throw "Missing cycle manifest for phase '$phaseName': $manifest"
      }
      $manifestObj = Get-Content -Path $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
      $manifestRunsRoot = [string]$manifestObj.runs_root
      Write-Host "== Phase: $phaseName =="
      $resumeEnabledForFirstPhase = (
        $ContinueFromLatestCheckpoint -or
        (-not [string]::IsNullOrWhiteSpace($startPhaseNorm))
      )
      $isCurriculumFirstPhase = ([string]$phaseName -eq [string]$firstPhaseName)
      if ($isCurriculumFirstPhase -and -not $AllowPhase1Resume) {
        # Safety default: phase1 should start fresh unless explicitly allowed.
        $resumeEnabledForFirstPhase = $false
        $resumeCheckpoint = $null
      }
      if (
        [string]::IsNullOrWhiteSpace([string]$resumeCheckpoint) -and
        $resumeEnabledForFirstPhase
      ) {
        $triedStrictPrevPhaseLookup = $false
        if (
          -not [string]::IsNullOrWhiteSpace([string]$startPhaseNorm) -and
          -not [string]::IsNullOrWhiteSpace([string]$prevPhaseName)
        ) {
          $triedStrictPrevPhaseLookup = $true
          $resumeFromPrevPhase = Resolve-CheckpointFromCycleTrainLog -RepoRoot $Repo -CurriculumName $curriculumName -PhaseName $prevPhaseName
          if (-not [string]::IsNullOrWhiteSpace([string]$resumeFromPrevPhase)) {
            $resumeCheckpoint = [string]$resumeFromPrevPhase
            Write-Host ("Resume checkpoint resolved from previous phase cycle ({0}): {1}" -f $prevPhaseName, [string]$resumeCheckpoint)
          } elseif ($StrictPhaseResume) {
            throw ("StrictPhaseResume: unable to resolve checkpoint from previous phase cycle '{0}' for start phase '{1}' in curriculum '{2}'." -f $prevPhaseName, $phaseName, $curriculumName)
          }
        }
      }
      if (
        [string]::IsNullOrWhiteSpace([string]$resumeCheckpoint) -and
        $resumeEnabledForFirstPhase
      ) {
        $resumeCheckpoint = Resolve-LatestCheckpointPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot
      }
      if ($isCurriculumFirstPhase -and [string]::IsNullOrWhiteSpace([string]$resumeCheckpoint)) {
        Write-Host "[Cycle] phase1 starts clean (no resume checkpoint)."
      }
      $manifestToRun = $manifest
      if (-not $DryRun -and -not [string]::IsNullOrWhiteSpace([string]$resumeCheckpoint)) {
        $trainCmd = [string]$manifestObj.train_command
        $m = [regex]::Match($trainCmd, "--config\s+(""(?<cfg>[^""]+)""|(?<cfg>\S+))")
        if ($m.Success) {
          $cfgPath = [string]$m.Groups["cfg"].Value
          $overlayCfg = Build-ResumeOverlayConfig -RepoRoot $Repo -BaseConfigPath $cfgPath -ResumeCheckpoint ([string]$resumeCheckpoint) -PhaseName $phaseName
          $manifestObj.train_command = Set-TrainConfigInCommand -TrainCommand $trainCmd -NewConfigPath $overlayCfg
          Write-Host ("Resume checkpoint for phase '{0}': {1}" -f $phaseName, [string]$resumeCheckpoint)
          $manifestTmpDir = Join-Path $Repo "runs_curriculum\experiments\curriculum_runtime_manifests"
          New-Item -ItemType Directory -Path $manifestTmpDir -Force | Out-Null
          $manifestTmp = Join-Path $manifestTmpDir ("manifest_{0}_{1}.json" -f $phaseName, (Get-Date -Format "yyyyMMdd_HHmmss"))
          ($manifestObj | ConvertTo-Json -Depth 16) | Set-Content -Path $manifestTmp -Encoding UTF8
          $manifestToRun = $manifestTmp
        }
      }
      $cmd = "powershell -ExecutionPolicy Bypass -File .\scripts\run_curriculum_cycle.ps1 -ManifestPath `"$manifestToRun`""
      if ($DryRun) { $cmd += " -DryRun" }
      $phaseStartedAtUtc = (Get-Date).ToUniversalTime().AddMinutes(-2)
      Invoke-Expression $cmd
      if ($LASTEXITCODE -ne 0) {
        throw "Phase run failed: $phaseName"
      }
      if ($DryRun) { continue }

      $benchLatest = Resolve-BenchPayloadPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot -PhaseName $phaseName -NotBeforeUtc $phaseStartedAtUtc
      if ([string]::IsNullOrWhiteSpace($benchLatest)) {
        throw "Missing benchmark payload after phase '$phaseName'. Checked bench_latest and bench_eval_*.json under runs roots."
      }
      Write-Host ("Bench payload used for gate: " + [string]$benchLatest)
      $bench = Get-Content -Path $benchLatest -Raw -Encoding UTF8 | ConvertFrom-Json
      $evalRunId = Resolve-RunIdFromPath -PathText ([string]$benchLatest)
      $expectedScenarioIds = @()
      $evalCfgPath = ""
      if ($manifestObj -ne $null) {
        $evalCfgPath = Resolve-CommandArgValue -Command ([string]$manifestObj.eval_command) -ArgName "--config"
      }
      $evalCfgObj = Get-YamlObject -YamlPath $evalCfgPath
      if ($evalCfgObj -and $evalCfgObj.benchmark -and $evalCfgObj.benchmark.scenario_ids) {
        $expectedScenarioIds = @(
          @($evalCfgObj.benchmark.scenario_ids) |
            ForEach-Object { [string]$_ } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
        )
      }
      $gate = Evaluate-Gate -BenchPayload $bench -GateSpec $phase.gate -PrevMetrics $prevMetrics -ExpectedScenarioIds $expectedScenarioIds
      $currentGateMetrics = $gate.metrics
      if (-not $gate.ok) {
        $phaseGateResult = "FAIL"
        $phaseGateReasons = @($gate.reasons)
        $promotionDecision = "hold"
        $promotionReason = "hard_gate_fail"
        Write-Host ""
        Write-Host "GATE FAILED at phase: $phaseName" -ForegroundColor Red
        foreach ($r in @($gate.reasons)) { Write-Host (" - " + [string]$r) -ForegroundColor Red }
        $gateFailures.Add(
          @{
            phase = [string]$phaseName
            reasons = @($gate.reasons)
            bench_payload = [string]$benchLatest
          }
        ) | Out-Null
        if ($StopOnGateFail) {
          throw "Stopped by gate at phase '$phaseName'."
        }
        Write-Host ("[Gate] continuing despite failure in phase '{0}' (StopOnGateFail not set)." -f $phaseName) -ForegroundColor Yellow
      $resumeCheckpoint = Resolve-LatestCheckpointPathSince -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot -NotBeforeUtc $phaseStartedAtUtc
      if ([string]::IsNullOrWhiteSpace([string]$resumeCheckpoint)) {
        $resumeCheckpoint = Resolve-LatestCheckpointPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot
      }
      $trainRunId = Resolve-RunIdFromPath -PathText ([string]$resumeCheckpoint)
        continue
      }
      $phaseGateResult = "PASS"
      $phaseGateReasons = @()
      $promotionDecision = "promote"
      $promotionReason = "hard_gate_pass"
      $prevMetrics = $gate.metrics
    $resumeCheckpoint = Resolve-LatestCheckpointPathSince -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot -NotBeforeUtc $phaseStartedAtUtc
    if ([string]::IsNullOrWhiteSpace([string]$resumeCheckpoint)) {
      $resumeCheckpoint = Resolve-LatestCheckpointPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot
    }
      $trainRunId = Resolve-RunIdFromPath -PathText ([string]$resumeCheckpoint)
      $checkpointPathUsed = [string]$resumeCheckpoint
      Write-Host ("Gate PASS | score={0:N3} timeout={1:N3} non_timeout_resolve={2:N3} resolved_non_timeout_win={3:N3} loss={4:N3} vp_take={5:N3} tracked_cap={6:N3} vp_net_tracked={7:N3}" -f `
        [double]$prevMetrics.score, [double]$prevMetrics.timeout_rate, [double]$prevMetrics.non_timeout_resolution_rate, [double]$prevMetrics.resolved_non_timeout_win_rate, [double]$prevMetrics.loss_rate, [double]$prevMetrics.vp_capture_take_rate, [double]$prevMetrics.tracked_captured_avg, [double]$prevMetrics.vp_net_avg_tracked_side)
    } catch {
      $errMsg = [string]$_.Exception.Message
      $phaseGateResult = "FAIL"
      $phaseGateReasons = @($errMsg)
      $promotionDecision = "rollback"
      $promotionReason = "phase_execution_error"
      Write-Host ("[Phase][ERROR] phase={0} error={1}" -f $phaseName, $errMsg) -ForegroundColor Red
      $phaseFailures.Add(
        @{
          phase = [string]$phaseName
          error = $errMsg
        }
      ) | Out-Null
      if ($StopOnPhaseError) {
        throw
      }
      Write-Host ("[Phase] continuing after phase error in '{0}' (StopOnPhaseError not set)." -f $phaseName) -ForegroundColor Yellow
      continue
    } finally {
      if (-not $DryRun) {
        $phaseEndUtc = (Get-Date).ToUniversalTime()
        $scenarioMixIds = @()
        $scenarioMixWeights = @()
        $matchupProfilesEnabled = @()
        $seedsHash = ""
        $trainConfigPath = ""
        $benchConfigPath = ""
        if ($manifestObj -ne $null) {
          $trainConfigPath = Resolve-CommandArgValue -Command ([string]$manifestObj.train_command) -ArgName "--config"
          $benchConfigPath = Resolve-CommandArgValue -Command ([string]$manifestObj.eval_command) -ArgName "--config"
        }
        $trainCfg = Get-YamlObject -YamlPath $trainConfigPath
        if ($trainCfg -and $trainCfg.scenario -and $trainCfg.scenario.ids) {
          $scenarioMixIds = @($trainCfg.scenario.ids | ForEach-Object { [string]$_ })
          if ($trainCfg.scenario.weights) {
            $scenarioMixWeights = @($trainCfg.scenario.weights | ForEach-Object { [double]$_ })
          }
        } elseif ($trainCfg -and $trainCfg.scenario_id) {
          $scenarioMixIds = @([string]$trainCfg.scenario_id)
        } elseif ($bench -and $bench.scenario_id) {
          $scenarioMixIds = @([string]$bench.scenario_id)
        }
        if ($trainCfg -and $trainCfg.selfplay -and $trainCfg.selfplay.matchup_modes) {
          $matchupProfilesEnabled = @($trainCfg.selfplay.matchup_modes | ForEach-Object { [string]$_ })
        }
        $benchCfg = Get-YamlObject -YamlPath $benchConfigPath
        if ($benchCfg -and $benchCfg.benchmark -and $benchCfg.benchmark.seeds) {
          $seedJson = ConvertTo-CompactJson @($benchCfg.benchmark.seeds)
          $seedsHash = Get-Sha1Hex12 -Text $seedJson
        }
        $diagStatus = "OK"
        $diagWarnings = @()
        $diagTimeout = $null
        if ($currentGateMetrics -and $currentGateMetrics.timeout_rate -ne $null) {
          $diagTimeout = [double]$currentGateMetrics.timeout_rate
          if ($diagTimeout -gt 0.85) {
            $diagStatus = "WARN"
            $diagWarnings += ("timeout_rate_high:" + [string]$diagTimeout)
          }
        }
        $traceRow = [ordered]@{
          schema_version = "curriculum_traceability.v1"
          recorded_at_utc = (Get-Date).ToUniversalTime().ToString("o")
          curriculum_name = [string]$curriculumName
          curriculum_version = [string]$curriculumVersion
          phase_name = [string]$phaseName
          phase_index = [int]($phaseIdx + 1)
          phase_started_at = $phaseStartUtc.ToString("o")
          phase_finished_at = $phaseEndUtc.ToString("o")
          train_run_id = [string]$trainRunId
          eval_run_id = [string]$evalRunId
          checkpoint_path = [string]$checkpointPathUsed
          scenario_mix_ids = @($scenarioMixIds)
          scenario_mix_weights = @($scenarioMixWeights)
          matchup_profiles_enabled = @($matchupProfilesEnabled)
          seeds_hash = [string]$seedsHash
          gate_spec_snapshot = $phase.gate
          gate_result_status = [string]$phaseGateResult
          gate_fail_reasons = @($phaseGateReasons)
          promotion_decision = [string]$promotionDecision
          promotion_reason = [string]$promotionReason
          baseline_reference = [string]$startPhaseNorm
          hard_gate_badge = ("HARD GATE: " + [string]$phaseGateResult)
          diagnostic_status = [string]$diagStatus
          diagnostic_badge = ("DIAGNOSTIC: " + [string]$diagStatus)
          diagnostic_warnings = @($diagWarnings)
          diagnostic_metrics = @{
            timeout_rate = $diagTimeout
            non_timeout_resolution_rate = if ($currentGateMetrics) { $currentGateMetrics.non_timeout_resolution_rate } else { $null }
            resolved_non_timeout_win_rate = if ($currentGateMetrics) { $currentGateMetrics.resolved_non_timeout_win_rate } else { $null }
          }
          gate_metrics = if ($currentGateMetrics) { $currentGateMetrics } else { @{} }
          bench_payload_path = [string]$benchLatest
          curriculum_yaml = [string]$curriculumPathResolved
          event = "phase_completed"
        }
        Write-CurriculumTraceRow -RepoRoot $Repo -Row $traceRow
      }
    }
  }

  if (-not $DryRun) {
    Write-Host ""
    if ($gateFailures.Count -eq 0) {
      Write-Host "All curriculum phases completed with gate PASS." -ForegroundColor Green
    } else {
      Write-Host ("Curriculum completed with {0} gate failure(s):" -f $gateFailures.Count) -ForegroundColor Yellow
      foreach ($gf in $gateFailures) {
        Write-Host (" - phase={0}" -f [string]$gf.phase) -ForegroundColor Yellow
        foreach ($reason in @($gf.reasons)) {
          Write-Host ("    * {0}" -f [string]$reason) -ForegroundColor Yellow
        }
      }
      Write-Host "Run with -StopOnGateFail to stop at first gate failure." -ForegroundColor Yellow
    }
    if ($phaseFailures.Count -gt 0) {
      Write-Host ("Curriculum completed with {0} phase error(s):" -f $phaseFailures.Count) -ForegroundColor Yellow
      foreach ($pf in $phaseFailures) {
        Write-Host (" - phase={0} error={1}" -f [string]$pf.phase, [string]$pf.error) -ForegroundColor Yellow
      }
      Write-Host "Run with -StopOnPhaseError to stop at first phase error." -ForegroundColor Yellow
    }
  }
}
finally {
  Pop-Location
}
