param(
  [string]$ManifestPath = ".\scripts\curriculum_cycle.template.json",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-LoggedCommand {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string]$LogPath
  )
  "`n>>> $Command`n" | Tee-Object -FilePath $LogPath -Append | Out-Null
  $prevEap = $ErrorActionPreference
  try {
    # Some tools (e.g. mlflow) write informational lines to stderr.
    # Execute natively via cmd.exe /c to stream merged stdout/stderr cleanly to Tee-Object
    # without PowerShell ErrorRecord wrapping or pipe buffer corruption on Windows.
    $ErrorActionPreference = "Continue"
    cmd.exe /c "$Command 2>&1" | Tee-Object -FilePath $LogPath -Append
  } finally {
    $ErrorActionPreference = $prevEap
  }
  if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host ("[Cycle][ERROR] command failed with exit={0}" -f $LASTEXITCODE) -ForegroundColor Red
    Write-Host ("[Cycle][ERROR] log: {0}" -f $LogPath) -ForegroundColor Red
    if (Test-Path $LogPath) {
      Write-Host "[Cycle][ERROR] ---- log tail (last 120 lines) ----" -ForegroundColor Yellow
      Get-Content -Path $LogPath -Tail 120
      Write-Host "[Cycle][ERROR] ---- end log tail ----" -ForegroundColor Yellow
    }
    throw "Command failed (exit=$LASTEXITCODE): $Command"
  }
}

function Resolve-BenchPayloadPath {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$RunsRoot
  )
  $benchLatest = Join-Path $RepoRoot (Join-Path $RunsRoot "bench_latest.json")
  if (Test-Path $benchLatest) { return $benchLatest }
  $xaiRoots = Get-ChildItem -Path (Join-Path $RepoRoot $RunsRoot) -Directory -ErrorAction SilentlyContinue
  $candidates = @()
  foreach ($rd in $xaiRoots) {
    $xai = Join-Path $rd.FullName "xai"
    if (-not (Test-Path $xai)) { continue }
    $candidates += Get-ChildItem -Path $xai -File -Filter "bench_eval_*.json" -ErrorAction SilentlyContinue
  }
  if (-not $candidates -or $candidates.Count -eq 0) { return $null }
  $latest = $candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  return [string]$latest.FullName
}

function Resolve-LatestCheckpointPath {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$RunsRoot
  )
  $root = Join-Path $RepoRoot $RunsRoot
  if (-not (Test-Path $root)) { return $null }
  $finals = Get-ChildItem -Path $root -Recurse -File -Filter "final.pt" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "(efficientzero_v2_|muzero_).+\\checkpoints\\final\.pt$" }
  if ($finals -and $finals.Count -gt 0) {
    return [string](($finals | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).FullName)
  }
  $iters = Get-ChildItem -Path $root -Recurse -File -Filter "iter_*.pt" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "(efficientzero_v2_|muzero_).+\\checkpoints\\iter_\d+\.pt$" }
  if ($iters -and $iters.Count -gt 0) {
    return [string](($iters | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).FullName)
  }
  return $null
}

function Set-OrAppendCommandArg {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string]$ArgName,
    [Parameter(Mandatory = $true)][string]$ArgValue
  )
  $quoted = '"' + [string]$ArgValue + '"'
  $pattern = [regex]::Escape($ArgName) + "\s+(""[^""]+""|\S+)"
  if ([regex]::IsMatch($Command, $pattern)) {
    return [regex]::Replace($Command, $pattern, ($ArgName + " " + $quoted), 1)
  }
  return ($Command + " " + $ArgName + " " + $quoted)
}

function Show-ControllersBySideFromBench {
  param(
    [string]$BenchPayloadPath
  )
  if ([string]::IsNullOrWhiteSpace([string]$BenchPayloadPath)) {
    Write-Host "[Cycle][WARN] controller_by_side report skipped: bench payload path is empty"
    return
  }
  if (-not (Test-Path $BenchPayloadPath)) {
    Write-Host ("[Cycle][WARN] controller_by_side report skipped: bench payload not found: {0}" -f [string]$BenchPayloadPath)
    return
  }
  try {
    $bench = Get-Content -Path $BenchPayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $rows = @($bench.results)
    if (-not $rows -or $rows.Count -eq 0) {
      Write-Host "[Cycle] controller_by_side: no result rows in bench payload"
      return
    }
    Write-Host "[Cycle] controller_by_side by result row:"
    foreach ($r in $rows) {
      $agent = [string]$r.agent_name
      $profile = [string]$r.matchup_profile
      $controllers = @{}
      if ($r.controller_by_side) {
        $controllers = $r.controller_by_side
      } elseif ($r.policy_by_side) {
        foreach ($p in $r.policy_by_side.PSObject.Properties) {
          $policy = [string]$p.Value
          $label = "Unknown"
          if ($policy -eq "mcts") { $label = "MuZero" }
          elseif ($policy -eq "random") { $label = "Random" }
          $controllers[$p.Name] = $label
        }
      }
      $pairs = @()
      foreach ($kv in $controllers.PSObject.Properties) {
        $pairs += ("{0}={1}" -f [string]$kv.Name, [string]$kv.Value)
      }
      $pairsTxt = if ($pairs.Count -gt 0) { ($pairs -join ", ") } else { "<missing>" }
      Write-Host ("  - agent={0} profile={1} controllers[{2}]" -f $agent, $profile, $pairsTxt)
    }
  } catch {
    Write-Host ("[Cycle][WARN] unable to print controller_by_side from bench payload: {0}" -f [string]$_.Exception.Message)
  }
}

if (-not (Test-Path $ManifestPath)) {
  throw "Manifest not found: $ManifestPath"
}

$manifestRaw = Get-Content -Path $ManifestPath -Raw -Encoding UTF8
$manifest = $manifestRaw | ConvertFrom-Json
if ($null -eq $manifest) {
  throw "Invalid manifest JSON: $ManifestPath"
}

$repo = [string]$manifest.repo
if ([string]::IsNullOrWhiteSpace($repo)) { $repo = (Get-Location).Path }
if (-not (Test-Path $repo)) { throw "Repo path not found: $repo" }

$name = [string]$manifest.name
if ([string]::IsNullOrWhiteSpace($name)) { throw "Manifest field 'name' is required." }

$runsRoot = [string]$manifest.runs_root
if ([string]::IsNullOrWhiteSpace($runsRoot)) { $runsRoot = "runs_curriculum" }

$trainCommand = [string]$manifest.train_command
$evalCommand = [string]$manifest.eval_command
$publishCommand = [string]$manifest.publish_command
if ([string]::IsNullOrWhiteSpace($trainCommand)) { throw "Manifest field 'train_command' is required." }
if ([string]::IsNullOrWhiteSpace($evalCommand)) { throw "Manifest field 'eval_command' is required." }

$trackedFiles = @()
if ($manifest.tracked_files) {
  foreach ($f in $manifest.tracked_files) {
    $trackedFiles += [string]$f
  }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeName = ($name -replace "[^a-zA-Z0-9._-]", "_")
$cycleId = "$timestamp" + "_" + $safeName
$cycleDir = Join-Path $repo (Join-Path $runsRoot ("experiments\curriculum_cycles\" + $cycleId))
$logsDir = Join-Path $cycleDir "logs"
$metaDir = Join-Path $cycleDir "meta"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
New-Item -ItemType Directory -Path $metaDir -Force | Out-Null

$trainLog = Join-Path $logsDir "01_train.log"
$evalLog = Join-Path $logsDir "02_eval.log"
$publishLog = Join-Path $logsDir "03_publish.log"

Push-Location $repo
try {
  $gitCommit = ""
  try {
    $gitCommit = (git rev-parse HEAD).Trim()
  } catch {
    $gitCommit = "unknown"
  }

  $tracked = @()
  foreach ($rel in $trackedFiles) {
    $abs = Join-Path $repo $rel
    if (-not (Test-Path $abs)) {
      $tracked += @{
        path = $rel
        exists = $false
        sha256 = $null
      }
      continue
    }
    $h = (Get-FileHash -Path $abs -Algorithm SHA256).Hash
    $tracked += @{
      path = $rel
      exists = $true
      sha256 = $h
    }
  }

  $lock = [ordered]@{
    cycle_id = $cycleId
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    repo = $repo
    git_commit = $gitCommit
    runs_root = $runsRoot
    manifest_path = (Resolve-Path $ManifestPath).Path
    manifest = $manifest
    tracked_files = $tracked
    dry_run = [bool]$DryRun
  }
  ($lock | ConvertTo-Json -Depth 64) | Set-Content -Path (Join-Path $metaDir "manifest.lock.json") -Encoding UTF8
  $manifestRaw | Set-Content -Path (Join-Path $metaDir "manifest.input.json") -Encoding UTF8

  if ($DryRun) {
    Write-Host "DryRun OK. Cycle prepared at: $cycleDir"
    Write-Host "Train command: $trainCommand"
    Write-Host "Eval command:  $evalCommand"
    if ([string]::IsNullOrWhiteSpace($publishCommand)) {
      Write-Host "Publish command: <skipped (auto or external)>"
    } else {
      Write-Host "Publish command: $publishCommand"
    }
    return
  }

  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Invoke-LoggedCommand -Command $trainCommand -LogPath $trainLog
  $latestCheckpoint = Resolve-LatestCheckpointPath -RepoRoot $repo -RunsRoot $runsRoot
  if ([string]::IsNullOrWhiteSpace([string]$latestCheckpoint)) {
    throw "No checkpoint found under runs root '$runsRoot' after train."
  }
  $evalCommandWithCheckpoint = Set-OrAppendCommandArg -Command $evalCommand -ArgName "--checkpoint" -ArgValue ([string]$latestCheckpoint)
  Invoke-LoggedCommand -Command $evalCommandWithCheckpoint -LogPath $evalLog
  $benchPayloadPath = Resolve-BenchPayloadPath -RepoRoot $repo -RunsRoot $runsRoot
  Show-ControllersBySideFromBench -BenchPayloadPath ([string]$benchPayloadPath)
  if ([string]::IsNullOrWhiteSpace($publishCommand)) {
    ">>> publish skipped (auto or external)" | Tee-Object -FilePath $publishLog -Append | Out-Null
  } else {
    Invoke-LoggedCommand -Command $publishCommand -LogPath $publishLog
  }

  $status = [ordered]@{
    cycle_id = $cycleId
    finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    status = "ok"
    logs = @{
      train = $trainLog
      eval = $evalLog
      publish = $publishLog
    }
  }
  ($status | ConvertTo-Json -Depth 16) | Set-Content -Path (Join-Path $metaDir "status.json") -Encoding UTF8

  Write-Host "Cycle completed: $cycleId"
  Write-Host "Artifacts: $cycleDir"
}
catch {
  $status = [ordered]@{
    cycle_id = $cycleId
    finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    status = "failed"
    error = [string]$_.Exception.Message
    logs = @{
      train = $trainLog
      eval = $evalLog
      publish = $publishLog
    }
  }
  ($status | ConvertTo-Json -Depth 16) | Set-Content -Path (Join-Path $metaDir "status.json") -Encoding UTF8
  throw
}
finally {
  Pop-Location
}
