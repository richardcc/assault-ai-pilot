[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Phase1Manifest = "curriculums/self_vs_self_vs_random_v1/cycles/phase1_bootstrap.cycle.json",
  [string[]]$Profiles = @(
    "curriculums/self_vs_self_vs_random_v1/configs/efficientzero_v2.phase1_bootstrap.capture_conservative.yaml",
    "curriculums/self_vs_self_vs_random_v1/configs/efficientzero_v2.phase1_bootstrap.capture_balanced.yaml",
    "curriculums/self_vs_self_vs_random_v1/configs/efficientzero_v2.phase1_bootstrap.capture_aggressive.yaml"
  ),
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Get-ProfileLabel {
  param([string]$ConfigPath)
  $name = [System.IO.Path]::GetFileNameWithoutExtension([string]$ConfigPath)
  if ([string]::IsNullOrWhiteSpace($name)) { return "unknown_profile" }
  return [string]$name
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

function Read-BenchPayload {
  param([string]$BenchPath)
  if (-not (Test-Path -LiteralPath $BenchPath)) {
    throw "Missing bench payload: $BenchPath"
  }
  $raw = Get-Content -LiteralPath $BenchPath -Raw -Encoding UTF8
  if ([string]::IsNullOrWhiteSpace($raw)) {
    throw "Bench payload is empty: $BenchPath"
  }
  return ($raw | ConvertFrom-Json)
}

function Resolve-BenchPayloadPath {
  param(
    [string]$RepoRoot,
    [datetime]$NotBeforeUtc
  )
  $candidates = @(
    (Join-Path $RepoRoot "runs_curriculum\bench_latest.json"),
    (Join-Path $RepoRoot "runs\bench_latest.json")
  )
  foreach ($p in $candidates) {
    if (Test-Path -LiteralPath $p) {
      $item = Get-Item -LiteralPath $p
      if ($item.LastWriteTimeUtc -ge $NotBeforeUtc) {
        return [string]$item.FullName
      }
    }
  }

  $roots = @(
    (Join-Path $RepoRoot "runs_curriculum"),
    (Join-Path $RepoRoot "runs")
  )
  $jsons = @()
  foreach ($r in $roots) {
    if (-not (Test-Path -LiteralPath $r)) { continue }
    $jsons += Get-ChildItem -Path $r -Recurse -File -Filter "bench_eval_*.json" -ErrorAction SilentlyContinue
  }
  if (-not $jsons -or $jsons.Count -eq 0) {
    return $null
  }
  $fresh = @($jsons | Where-Object { $_.LastWriteTimeUtc -ge $NotBeforeUtc })
  if ($fresh.Count -gt 0) {
    $jsons = $fresh
  }
  $latest = $jsons | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  if ($null -eq $latest) { return $null }
  return [string]$latest.FullName
}

function Select-MainResultRow {
  param([object]$BenchPayload)
  $rows = @($BenchPayload.results)
  if (-not $rows -or $rows.Count -eq 0) {
    throw "Bench payload has no result rows."
  }
  $main = $rows | Where-Object {
    $n = [string]($_.agent_name)
    $n -in @("efficientzero_v2_stub", "muzero_stub")
  } | Select-Object -First 1
  if ($null -eq $main) { $main = $rows | Select-Object -First 1 }
  return $main
}

function Get-KpiValue {
  param(
    [object]$Primary,
    [string[]]$CandidateKeys
  )
  foreach ($k in $CandidateKeys) {
    if ($null -eq $Primary) { break }
    $v = $Primary.PSObject.Properties[$k]
    if ($null -eq $v) { continue }
    $raw = $v.Value
    if ($null -eq $raw) { continue }
    try {
      return [double]$raw
    } catch {
      continue
    }
  }
  return [double]0.0
}

function Get-OptionalNumber {
  param(
    [object]$Primary,
    [string[]]$CandidateKeys
  )
  foreach ($k in $CandidateKeys) {
    if ($null -eq $Primary) { break }
    $v = $Primary.PSObject.Properties[$k]
    if ($null -eq $v) { continue }
    $raw = $v.Value
    if ($null -eq $raw) { return $null }
    try {
      return [double]$raw
    } catch {
      continue
    }
  }
  return $null
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $manifestAbs = Join-Path $Repo $Phase1Manifest
  if (-not (Test-Path -LiteralPath $manifestAbs)) {
    throw "Phase1 manifest not found: $manifestAbs"
  }

  $manifestBase = Get-Content -LiteralPath $manifestAbs -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($null -eq $manifestBase) {
    throw "Invalid phase1 manifest JSON: $manifestAbs"
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $outDir = Join-Path $Repo ("runs_curriculum\ab_capture_profiles\" + $stamp)
  $manifestsDir = Join-Path $outDir "manifests"
  $payloadsDir = Join-Path $outDir "payloads"
  New-Item -ItemType Directory -Path $outDir -Force | Out-Null
  New-Item -ItemType Directory -Path $manifestsDir -Force | Out-Null
  New-Item -ItemType Directory -Path $payloadsDir -Force | Out-Null

  $results = @()
  $allStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

  foreach ($cfgRel in $Profiles) {
    $cfgAbs = Join-Path $Repo $cfgRel
    if (-not (Test-Path -LiteralPath $cfgAbs)) {
      throw "Profile config not found: $cfgAbs"
    }
    $label = Get-ProfileLabel -ConfigPath $cfgRel
    Write-Host ""
    Write-Host ("== Capture AB | profile={0} ==" -f $label) -ForegroundColor Cyan

    $phaseManifest = $manifestBase.PSObject.Copy()
    $phaseManifest.name = [string]("{0}_{1}" -f [string]$manifestBase.name, [string]$label)
    $phaseManifest.train_command = Set-TrainConfigInCommand -TrainCommand ([string]$manifestBase.train_command) -NewConfigPath ([string]$cfgRel)
    $manifestOut = Join-Path $manifestsDir ("phase1_" + $label + ".cycle.json")
    ($phaseManifest | ConvertTo-Json -Depth 32) | Set-Content -LiteralPath $manifestOut -Encoding UTF8

    if ($DryRun) {
      Write-Host ("[DryRun] manifest generated: {0}" -f $manifestOut)
      continue
    }

    $runStartedAtUtc = (Get-Date).ToUniversalTime().AddMinutes(-2)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    & powershell -ExecutionPolicy Bypass -File ".\scripts\run_curriculum_cycle.ps1" -ManifestPath $manifestOut
    if ($LASTEXITCODE -ne 0) {
      throw ("run_curriculum_cycle failed for profile={0} exit={1}" -f $label, $LASTEXITCODE)
    }
    $sw.Stop()

    $benchLatest = Resolve-BenchPayloadPath -RepoRoot $Repo -NotBeforeUtc $runStartedAtUtc
    if ([string]::IsNullOrWhiteSpace([string]$benchLatest)) {
      throw "Could not resolve benchmark payload path for profile '$label'."
    }
    $benchPayload = Read-BenchPayload -BenchPath $benchLatest
    $row = Select-MainResultRow -BenchPayload $benchPayload
    $kpis = @{}
    if ($row.phase_2_9_eval_kpis) { $kpis = $row.phase_2_9_eval_kpis }

    $benchCopy = Join-Path $payloadsDir ("bench_" + $label + ".json")
    Copy-Item -LiteralPath $benchLatest -Destination $benchCopy -Force

    $results += [pscustomobject]@{
      profile = [string]$label
      config = [string]$cfgRel
      agent_name = [string]($row.agent_name)
      matchup_profile = [string]($row.matchup_profile)
      episodes = [int]($row.episodes)
      win_rate = [double](Get-KpiValue -Primary $row -CandidateKeys @("win_rate"))
      timeout_rate = [double](Get-KpiValue -Primary $row -CandidateKeys @("timeout_rate"))
      tracked_captured_avg = [double](Get-KpiValue -Primary $row -CandidateKeys @("tracked_captured_avg"))
      xai_vp_capture_take_rate = Get-OptionalNumber -Primary $kpis -CandidateKeys @("xai_vp_capture_take_rate")
      opportunity_conversion_early_opportunity_steps = [double](Get-KpiValue -Primary $kpis -CandidateKeys @("opportunity_conversion_early_opportunity_steps"))
      opportunity_conversion_early_converted_steps = [double](Get-KpiValue -Primary $kpis -CandidateKeys @("opportunity_conversion_early_converted_steps"))
      opportunity_conversion_early_rate = Get-OptionalNumber -Primary $kpis -CandidateKeys @("opportunity_conversion_early_rate")
      opportunity_conversion_mid_opportunity_steps = [double](Get-KpiValue -Primary $kpis -CandidateKeys @("opportunity_conversion_mid_opportunity_steps"))
      opportunity_conversion_mid_converted_steps = [double](Get-KpiValue -Primary $kpis -CandidateKeys @("opportunity_conversion_mid_converted_steps"))
      opportunity_conversion_mid_rate = Get-OptionalNumber -Primary $kpis -CandidateKeys @("opportunity_conversion_mid_rate")
      opportunity_conversion_late_opportunity_steps = [double](Get-KpiValue -Primary $kpis -CandidateKeys @("opportunity_conversion_late_opportunity_steps"))
      opportunity_conversion_late_converted_steps = [double](Get-KpiValue -Primary $kpis -CandidateKeys @("opportunity_conversion_late_converted_steps"))
      opportunity_conversion_late_rate = Get-OptionalNumber -Primary $kpis -CandidateKeys @("opportunity_conversion_late_rate")
      profile_wall_s = [double](Get-KpiValue -Primary $row -CandidateKeys @("profile_wall_s"))
      episode_wall_s_mean = [double](Get-KpiValue -Primary $row -CandidateKeys @("episode_wall_s_mean"))
      episodes_per_second = [double](Get-KpiValue -Primary $row -CandidateKeys @("episodes_per_second"))
      elapsed_s_total = [double]$sw.Elapsed.TotalSeconds
      bench_payload_path = [string]$benchCopy
    }
  }

  $allStopwatch.Stop()
  if ($DryRun) {
    Write-Host ""
    Write-Host ("Dry run completed. Output dir: {0}" -f $outDir) -ForegroundColor Yellow
    return
  }

  $summaryJson = Join-Path $outDir "summary_capture_ab.json"
  $summaryCsv = Join-Path $outDir "summary_capture_ab.csv"
  ($results | ConvertTo-Json -Depth 16) | Set-Content -LiteralPath $summaryJson -Encoding UTF8
  $results | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8

  Write-Host ""
  Write-Host "== Capture AB Summary ==" -ForegroundColor Green
  $results | Sort-Object -Property xai_vp_capture_take_rate -Descending |
    Format-Table profile, tracked_captured_avg, xai_vp_capture_take_rate, opportunity_conversion_early_opportunity_steps, opportunity_conversion_early_converted_steps, opportunity_conversion_early_rate, opportunity_conversion_mid_opportunity_steps, opportunity_conversion_mid_converted_steps, opportunity_conversion_mid_rate, opportunity_conversion_late_opportunity_steps, opportunity_conversion_late_converted_steps, opportunity_conversion_late_rate, timeout_rate, profile_wall_s, episode_wall_s_mean, elapsed_s_total -AutoSize |
    Out-String | Write-Host
  Write-Host ("Summary JSON: {0}" -f $summaryJson)
  Write-Host ("Summary CSV:  {0}" -f $summaryCsv)
  Write-Host ("Total elapsed: {0:n1}s" -f $allStopwatch.Elapsed.TotalSeconds)
}
finally {
  Pop-Location
}
