param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$CurriculumYaml = ".\curriculums\self_vs_self_vs_random_2scenarios_v1\curriculum.yaml",
  [string]$StartPhase = "",
  [switch]$ContinueFromLatestCheckpoint,
  [switch]$StrictPhaseResume,
  [switch]$AllowPhase1Resume,
  [switch]$StopOnGateFail,
  [switch]$StopOnPhaseError,
  [int]$DefaultMaxReinforcementCycles = 3,
  [string]$ExplicitStartCheckpoint = "",
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
  }
  $lossRate = $sumLoss / $den
  $trackedCapturedAvg = $sumTrackedCaptured / $den
  $trackedSide = [string]($main.tracked_side)
  $vpNetTrackedSide = $sumVpNetTracked / $den
  $vpCaptureTakeRate = $sumVpCapture / $den

  # Tactical Quality Score (TQS):
  # Standard composite evaluation:
  # 40% Win Rate + 40% Objective Capture Ratio (up to 3 VPs) + 20% Anti-Defeat (1 - lossRate)
  $vpRatio = [math]::Min(1.0, [math]::Max(0.0, ($trackedCapturedAvg / 3.0)))
  $antiLoss = [math]::Max(0.0, (1.0 - $lossRate))
  $tqs = (0.40 * $score) + (0.40 * $vpRatio) + (0.20 * $antiLoss)

  # Check gate conditions:
  if ($GateSpec.min_tqs -ne $null) {
    $th = [double]$GateSpec.min_tqs
    if ($tqs -lt $th) {
      $ok = $false
      $reasons.Add(("tqs (tactical_quality_score) {0:N3} < min_tqs {1:N3}" -f $tqs, $th))
    }
  }

  if ($GateSpec.max_loss_rate -ne $null) {
    $th = [double]$GateSpec.max_loss_rate
    if ($lossRate -gt $th) {
      $ok = $false
      $reasons.Add(("loss_rate {0:N3} > max_loss_rate {1:N3}" -f $lossRate, $th))
    }
  }

  if ($GateSpec.min_tracked_captured_avg -ne $null) {
    $th = [double]$GateSpec.min_tracked_captured_avg
    if ($trackedCapturedAvg -lt $th) {
      $ok = $false
      $reasons.Add(("tracked_captured_avg {0:N3} < min_tracked_captured_avg {1:N3}" -f $trackedCapturedAvg, $th))
    }
  }

  if ($GateSpec.min_score -ne $null) {
    $th = [double]$GateSpec.min_score
    if ($score -lt $th) {
      $ok = $false
      $reasons.Add(("score {0:N3} < min_score {1:N3}" -f $score, $th))
    }
  }

  if ($GateSpec.min_vp_capture_take_rate -ne $null) {
    $th = [double]$GateSpec.min_vp_capture_take_rate
    if ($vpCaptureTakeRate -lt $th) {
      $ok = $false
      $reasons.Add(("xai_vp_capture_take_rate {0:N3} < min_vp_capture_take_rate {1:N3}" -f $vpCaptureTakeRate, $th))
    }
  }

  if ($GateSpec.min_vp_net_avg_tracked_side -ne $null) {
    $th = [double]$GateSpec.min_vp_net_avg_tracked_side
    if ($vpNetTrackedSide -lt $th) {
      $ok = $false
      $reasons.Add(("vp_net_avg_tracked_side {0:N3} < min_vp_net_avg_tracked_side {1:N3}" -f $vpNetTrackedSide, $th))
    }
  }

  if ($GateSpec.no_regression_defeat_rate -eq $true -and $PrevMetrics) {
    $prevLoss = [double]$PrevMetrics.loss_rate
    if ($lossRate -gt $prevLoss) {
      $ok = $false
      $reasons.Add(("loss_rate regression: {0:N3} > previous {1:N3}" -f $lossRate, $prevLoss))
    }
  }

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
        $reasons.Add(("profile '$profileName' score {0:N3} < min {1:N3}" -f $profileScore, $thScore))
      }
    }
  }

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
          $reasons.Add(("profile '$profileName' severe floor: score {0:N3} < severe_min_score {1:N3}" -f $profileScore, $thSevere))
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
            $reasons.Add(("profile '$profileName' score drop {0:N3} > max_score_drop_vs_prev {1:N3}" -f $drop, $maxDrop))
          }
        }
      }
    }
  }

  return @{
    ok = $ok
    reasons = @($reasons)
    metrics = @{
      score = $score
      tqs = $tqs
      tactical_quality_score = $tqs
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
  param([string]$RepoRoot, [string]$RunsRootPreferred)
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
  param([string]$RepoRoot, [string]$RunsRootPreferred)
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

function Set-TrainConfigInCommand {
  param([string]$TrainCommand, [string]$NewConfigPath)
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
  $resolvedBase = $BaseConfigPath
  if (-not [System.IO.Path]::IsPathRooted($resolvedBase)) {
    $resolvedBase = Join-Path $RepoRoot $resolvedBase
  }
  if (-not (Test-Path $resolvedBase)) {
    throw "Base config does not exist for overlay: $BaseConfigPath"
  }
  $cfgDir = Join-Path $RepoRoot "runs_curriculum\experiments\curriculum_runtime_configs"
  New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
  $ts = (Get-Date).ToString("yyyyMMdd_HHmmss")
  $targetPath = Join-Path $cfgDir ("resume_overlay_{0}_{1}.yaml" -f $PhaseName, $ts)
  $basePosix = $resolvedBase.Replace("\", "/")
  $ckptPosix = $ResumeCheckpoint.Replace("\", "/")
  $content = @"
base_config: "$basePosix"
train:
  resume_checkpoint: "$ckptPosix"
"@
  Set-Content -Path $targetPath -Value $content -Encoding UTF8
  return $targetPath
}

# --- Main Dynamic Gated Progression Execution ---
Push-Location $Repo
try {
  $curriculumPathResolved = $CurriculumYaml
  if (-not [System.IO.Path]::IsPathRooted($curriculumPathResolved)) {
    $curriculumPathResolved = Join-Path $Repo $curriculumPathResolved
  }
  if (-not (Test-Path $curriculumPathResolved)) {
    throw "Curriculum YAML not found: $curriculumPathResolved"
  }
  $curriculum = Get-CurriculumJson -YamlPath $curriculumPathResolved
  $curriculumName = [string]$curriculum.name
  $curriculumVersion = if ($curriculum.version) { [string]$curriculum.version } else { "v1" }
  $phases = @($curriculum.phases)
  if ($phases.Count -eq 0) { throw "No phases defined in curriculum: $curriculumPathResolved" }

  $currDir = Split-Path -Parent $curriculumPathResolved
  $firstPhaseName = [string]$phases[0].name
  $started = [string]::IsNullOrWhiteSpace($StartPhase)
  $startPhaseNorm = [string]$StartPhase

  Write-Host "=================================================================" -ForegroundColor Cyan
  Write-Host " DYNAMIC GATED CURRICULUM RUNNER: $curriculumName" -ForegroundColor Cyan
  Write-Host " Policy: Reinforce on gate failure, promote ONLY on quality pass" -ForegroundColor Cyan
  Write-Host "=================================================================" -ForegroundColor Cyan

  $prevMetrics = $null
  $resumeCheckpoint = $null
  if (-not [string]::IsNullOrWhiteSpace($ExplicitStartCheckpoint) -and (Test-Path $ExplicitStartCheckpoint)) {
    $resumeCheckpoint = $ExplicitStartCheckpoint
    Write-Host ("Explicit start checkpoint supplied: {0}" -f $resumeCheckpoint) -ForegroundColor Magenta
  }

  $gateFailures = New-Object System.Collections.Generic.List[object]
  $phaseFailures = New-Object System.Collections.Generic.List[object]

  for ($phaseIdx = 0; $phaseIdx -lt $phases.Count; $phaseIdx++) {
    $phase = $phases[$phaseIdx]
    $phaseName = [string]$phase.name
    $prevPhaseName = if ($phaseIdx -gt 0) { [string]$phases[$phaseIdx - 1].name } else { "" }

    if (-not $started) {
      if ($phaseName -ne $startPhaseNorm) { continue }
      $started = $true
      Write-Host "Resuming from phase: $phaseName" -ForegroundColor Cyan
    }

    $manifest = Join-Path $currDir ("cycles\" + $phaseName + ".cycle.json")
    if (-not (Test-Path $manifest)) {
      throw "Missing cycle manifest for phase '$phaseName': $manifest"
    }
    $manifestObj = Get-Content -Path $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifestRunsRoot = [string]$manifestObj.runs_root

    # Determine max reinforcement cycles for this phase
    $maxCycles = $DefaultMaxReinforcementCycles
    if ($phase.max_reinforcement_cycles -ne $null) {
      $maxCycles = [int]$phase.max_reinforcement_cycles
    }
    if ($maxCycles -lt 1) { $maxCycles = 1 }

    # Setup initial checkpoint for phase 1 if required
    $isCurriculumFirstPhase = ([string]$phaseName -eq [string]$firstPhaseName)
    if ($isCurriculumFirstPhase -and [string]::IsNullOrWhiteSpace($resumeCheckpoint)) {
      if ($ContinueFromLatestCheckpoint -or $AllowPhase1Resume) {
        $resumeCheckpoint = Resolve-LatestCheckpointPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot
        if ($resumeCheckpoint) {
          Write-Host ("Phase 1 warm-starting from latest checkpoint: {0}" -f $resumeCheckpoint) -ForegroundColor Magenta
        }
      } else {
        Write-Host "[Cycle] Phase 1 starts clean (no resume checkpoint)."
      }
    }

    $cycleIteration = 1
    $phasePassed = $false

    # Dynamic Reinforcement Loop:
    while (-not $phasePassed -and $cycleIteration -le $maxCycles) {
      $phaseStartUtc = (Get-Date).ToUniversalTime()
      $phaseEndUtc = $null
      $phaseGateResult = "UNKNOWN"
      $phaseGateReasons = @()
      $promotionDecision = "hold"
      $promotionReason = ""
      $currentGateMetrics = @{}
      $benchLatest = ""
      $evalRunId = ""
      $trainRunId = ""
      $checkpointPathUsed = [string]$resumeCheckpoint

      Write-Host ""
      Write-Host ("-----------------------------------------------------------------") -ForegroundColor Green
      Write-Host (" [PHASE {0}/{1}] {2} | Cycle {3}/{4}" -f ($phaseIdx + 1), $phases.Count, $phaseName, $cycleIteration, $maxCycles) -ForegroundColor Green
      Write-Host ("-----------------------------------------------------------------") -ForegroundColor Green

      try {
        $manifestToRun = $manifest
        if (-not $DryRun -and -not [string]::IsNullOrWhiteSpace([string]$resumeCheckpoint)) {
          $trainCmd = [string]$manifestObj.train_command
          $m = [regex]::Match($trainCmd, "--config\s+(""(?<cfg>[^""]+)""|(?<cfg>\S+))")
          if ($m.Success) {
            $cfgPath = [string]$m.Groups["cfg"].Value
            $overlayCfg = Build-ResumeOverlayConfig -RepoRoot $Repo -BaseConfigPath $cfgPath -ResumeCheckpoint ([string]$resumeCheckpoint) -PhaseName ("{0}_c{1}" -f $phaseName, $cycleIteration)
            $manifestObj.train_command = Set-TrainConfigInCommand -TrainCommand $trainCmd -NewConfigPath $overlayCfg
            Write-Host ("Using checkpoint: {0}" -f [string]$resumeCheckpoint) -ForegroundColor Gray
            $manifestTmpDir = Join-Path $Repo "runs_curriculum\experiments\curriculum_runtime_manifests"
            New-Item -ItemType Directory -Path $manifestTmpDir -Force | Out-Null
            $manifestTmp = Join-Path $manifestTmpDir ("manifest_{0}_c{1}_{2}.json" -f $phaseName, $cycleIteration, (Get-Date -Format "yyyyMMdd_HHmmss"))
            ($manifestObj | ConvertTo-Json -Depth 16) | Set-Content -Path $manifestTmp -Encoding UTF8
            $manifestToRun = $manifestTmp
          }
        }

        $cmd = "powershell -ExecutionPolicy Bypass -File .\scripts\run_curriculum_cycle.ps1 -ManifestPath `"$manifestToRun`""
        if ($DryRun) { $cmd += " -DryRun" }
        $phaseStartedAtUtc = (Get-Date).ToUniversalTime().AddMinutes(-2)
        Invoke-Expression $cmd
        if ($LASTEXITCODE -ne 0) {
          throw "Phase cycle execution failed: $phaseName (cycle $cycleIteration)"
        }
        if ($DryRun) {
          $phasePassed = $true
          break
        }

        $benchLatest = Resolve-BenchPayloadPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot -PhaseName $phaseName -NotBeforeUtc $phaseStartedAtUtc
        if ([string]::IsNullOrWhiteSpace($benchLatest)) {
          throw "Missing benchmark payload after phase '$phaseName' cycle $cycleIteration."
        }
        $bench = Get-Content -Path $benchLatest -Raw -Encoding UTF8 | ConvertFrom-Json
        $evalRunId = Resolve-RunIdFromPath -PathText ([string]$benchLatest)

        # Expected scenarios from eval config
        $expectedScenarioIds = @()
        $evalCfgPath = Resolve-CommandArgValue -Command ([string]$manifestObj.eval_command) -ArgName "--config"
        $evalCfgObj = Get-YamlObject -YamlPath $evalCfgPath
        if ($evalCfgObj -and $evalCfgObj.benchmark -and $evalCfgObj.benchmark.scenario_ids) {
          $expectedScenarioIds = @(@($evalCfgObj.benchmark.scenario_ids) | ForEach-Object { [string]$_ } | Sort-Object -Unique)
        }

        # Evaluate quality gate
        $gate = Evaluate-Gate -BenchPayload $bench -GateSpec $phase.gate -PrevMetrics $prevMetrics -ExpectedScenarioIds $expectedScenarioIds
        $currentGateMetrics = $gate.metrics
        $tqsScore = [double]$currentGateMetrics.tqs
        $winRate = [double]$currentGateMetrics.score
        $defeatRate = [double]$currentGateMetrics.loss_rate
        $vpAvg = [double]$currentGateMetrics.tracked_captured_avg

        # Resolve the newly produced checkpoint from this cycle
        $newCheckpoint = Resolve-LatestCheckpointPathSince -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot -NotBeforeUtc $phaseStartedAtUtc
        if ([string]::IsNullOrWhiteSpace([string]$newCheckpoint)) {
          $newCheckpoint = Resolve-LatestCheckpointPath -RepoRoot $Repo -RunsRootPreferred $manifestRunsRoot
        }
        $trainRunId = Resolve-RunIdFromPath -PathText ([string]$newCheckpoint)

        if (-not $gate.ok) {
          $phaseGateResult = "FAIL"
          $phaseGateReasons = @($gate.reasons)
          $promotionDecision = "hold"
          $promotionReason = "gate_criteria_unmet"

          Write-Host ""
          Write-Host ("[Dynamic Gate][UNMET] Phase '{0}' (Cycle {1}/{2})" -f $phaseName, $cycleIteration, $maxCycles) -ForegroundColor Yellow
          Write-Host ("   Metrics: TQS={0:N3} | WinRate={1:N1}% | Defeats={2:N1}% | VPs={3:N2}" -f $tqsScore, ($winRate * 100), ($defeatRate * 100), $vpAvg) -ForegroundColor Yellow
          foreach ($r in @($gate.reasons)) {
            Write-Host ("   - [Unmet]: " + [string]$r) -ForegroundColor Yellow
          }

          if ($cycleIteration -lt $maxCycles) {
            Write-Host ""
            Write-Host ("[Dynamic Gate][REINFORCE] Accumulating reinforcement cycle ({0} -> {1}/{2})..." -f $cycleIteration, ($cycleIteration + 1), $maxCycles) -ForegroundColor Cyan
            Write-Host ("   Continuous learning resuming from checkpoint: {0}" -f $newCheckpoint) -ForegroundColor Cyan
            $resumeCheckpoint = $newCheckpoint
            $cycleIteration++
            continue
          } else {
            Write-Host ""
            Write-Host ("[Dynamic Gate][LIMIT] Maximum reinforcement cycles ({0}) reached without passing gate." -f $maxCycles) -ForegroundColor Red
            $gateFailures.Add(@{
              phase = [string]$phaseName
              cycles_attempted = $cycleIteration
              reasons = @($gate.reasons)
              bench_payload = [string]$benchLatest
            }) | Out-Null
            if ($StopOnGateFail) {
              throw "Stopped by gate at phase '$phaseName' after $maxCycles cycles."
            }
            Write-Host ("[Dynamic Gate] Advancing to next phase (StopOnGateFail not set).") -ForegroundColor Yellow
            $resumeCheckpoint = $newCheckpoint
            break
          }
        } else {
          # Gate PASSED!
          $phasePassed = $true
          $phaseGateResult = "PASS"
          $phaseGateReasons = @()
          $promotionDecision = "promote"
          $promotionReason = "dynamic_gate_passed"
          $prevMetrics = $gate.metrics
          $resumeCheckpoint = $newCheckpoint

          Write-Host ""
          Write-Host ("[Dynamic Gate][PROMOTED] PROMOTION GRANTED for Phase '{0}' on Cycle {1}/{2}!" -f $phaseName, $cycleIteration, $maxCycles) -ForegroundColor Green
          Write-Host ("   Quality Metrics: TQS={0:N3} (>= min_tqs) | WinRate={1:N1}% | Defeats={2:N1}% | VPs={3:N2}" -f $tqsScore, ($winRate * 100), ($defeatRate * 100), $vpAvg) -ForegroundColor Green
          Write-Host ("   Promoting checkpoint: {0}" -f $resumeCheckpoint) -ForegroundColor Green
          break
        }
      } catch {
        $errMsg = [string]$_.Exception.Message
        $phaseGateResult = "FAIL"
        $phaseGateReasons = @($errMsg)
        $promotionDecision = "error_hold"
        $promotionReason = "phase_execution_error"
        Write-Host ("[Phase][ERROR] phase={0} error={1}" -f $phaseName, $errMsg) -ForegroundColor Red
        $phaseFailures.Add(@{ phase = [string]$phaseName; error = $errMsg }) | Out-Null
        if ($StopOnPhaseError) { throw }
        Write-Host ("[Phase] Continuing after phase error in '{0}' (StopOnPhaseError not set)." -f $phaseName) -ForegroundColor Yellow
        break
      } finally {
        if (-not $DryRun) {
          $phaseEndUtc = (Get-Date).ToUniversalTime()
          $traceRow = [ordered]@{
            schema_version = "curriculum_traceability.v2"
            recorded_at_utc = (Get-Date).ToUniversalTime().ToString("o")
            curriculum_name = [string]$curriculumName
            curriculum_version = [string]$curriculumVersion
            phase_name = [string]$phaseName
            phase_index = [int]($phaseIdx + 1)
            cycle_iteration = [int]$cycleIteration
            max_reinforcement_cycles = [int]$maxCycles
            phase_started_at = $phaseStartUtc.ToString("o")
            phase_finished_at = $phaseEndUtc.ToString("o")
            train_run_id = [string]$trainRunId
            eval_run_id = [string]$evalRunId
            checkpoint_path = [string]$checkpointPathUsed
            tactical_quality_score = [double]$tqsScore
            gate_spec_snapshot = $phase.gate
            gate_result_status = [string]$phaseGateResult
            gate_fail_reasons = @($phaseGateReasons)
            promotion_decision = [string]$promotionDecision
            promotion_reason = [string]$promotionReason
            gate_metrics = if ($currentGateMetrics) { $currentGateMetrics } else { @{} }
            bench_payload_path = [string]$benchLatest
            curriculum_yaml = [string]$curriculumPathResolved
            event = "phase_cycle_evaluated"
          }
          Write-CurriculumTraceRow -RepoRoot $Repo -Row $traceRow
        }
      }
    } # end while reinforcement loop
  } # end for phase

  Write-Host ""
  Write-Host "=================================================================" -ForegroundColor Cyan
  Write-Host " CURRICULUM RUN SUMMARY" -ForegroundColor Cyan
  Write-Host "=================================================================" -ForegroundColor Cyan
  if ($gateFailures.Count -eq 0) {
    Write-Host "All phases passed dynamic quality gates successfully!" -ForegroundColor Green
  } else {
    Write-Host ("Completed with {0} phase(s) hitting maximum cycle limits:" -f $gateFailures.Count) -ForegroundColor Yellow
    foreach ($gf in $gateFailures) {
      Write-Host (" - Phase: {0} (Cycles: {1})" -f $gf.phase, $gf.cycles_attempted) -ForegroundColor Yellow
    }
  }
} finally {
  Pop-Location
}
