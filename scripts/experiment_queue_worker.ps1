[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [string]$ManifestsDir = ".\scripts\experiments",
  [int]$PollSeconds = 10,
  [switch]$ApplyChanges,
  [switch]$ForceOldMismatch,
  [switch]$IgnoreRunningGuard,
  [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath does not exist: $RepoPath"
}

if ($PollSeconds -lt 1) {
  throw "PollSeconds must be >= 1"
}

$batchScript = Join-Path $RepoPath "scripts\run_experiment_batch.ps1"
if (-not (Test-Path -Path $batchScript -PathType Leaf)) {
  throw "Batch script not found: $batchScript"
}

$workerRoot = Join-Path $RepoPath "assault_sim\session\reports\experiments\worker"
New-Item -ItemType Directory -Path $workerRoot -Force | Out-Null
$lockPath = Join-Path $workerRoot "queue_worker.lock"
$heartbeatPath = Join-Path $workerRoot "queue_worker.heartbeat.json"
$workerLogPath = Join-Path $workerRoot "queue_worker.log"

function Write-Heartbeat {
  param(
    [string]$State,
    [string]$Detail = "",
    [int]$Pending = 0,
    [string[]]$PendingSamples = @()
  )
  $payload = [ordered]@{
    pid = $PID
    state = $State
    detail = $Detail
    pending = $Pending
    pending_samples = @($PendingSamples | Select-Object -First 5)
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
  }
  ($payload | ConvertTo-Json -Depth 4) | Out-File -FilePath $heartbeatPath -Encoding UTF8
}

function Append-WorkerLog {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
  $line | Out-File -FilePath $workerLogPath -Append -Encoding UTF8
  Write-Host $line
}

function Resolve-ManifestsPath {
  param(
    [string]$RepoRoot,
    [string]$DirPath
  )
  if ([System.IO.Path]::IsPathRooted($DirPath)) {
    return $DirPath
  }
  return (Join-Path $RepoRoot $DirPath)
}

function Get-PendingManifestCount {
  param([string]$DirPath)
  if (-not (Test-Path -Path $DirPath -PathType Container)) { return 0 }
  $count = 0
  $files = @(Get-ChildItem -Path $DirPath -Filter "*.json" -File -ErrorAction SilentlyContinue)
  foreach ($f in $files) {
    try {
      $obj = Get-Content -Path $f.FullName -Raw | ConvertFrom-Json
      $status = [string]$obj.status
      if ($status -eq "planned" -or [string]::IsNullOrWhiteSpace($status)) {
        $count += 1
      }
    }
    catch {
      # Ignore malformed files here; batch validation handles failures explicitly.
      continue
    }
  }
  return $count
}

function Get-PendingManifestNames {
  param([string]$DirPath)
  $names = New-Object System.Collections.Generic.List[string]
  if (-not (Test-Path -Path $DirPath -PathType Container)) { return $names }
  $files = @(Get-ChildItem -Path $DirPath -Filter "*.json" -File -ErrorAction SilentlyContinue | Sort-Object Name)
  foreach ($f in $files) {
    try {
      $obj = Get-Content -Path $f.FullName -Raw | ConvertFrom-Json
      $status = [string]$obj.status
      if ($status -eq "planned" -or [string]::IsNullOrWhiteSpace($status)) {
        $names.Add($f.Name) | Out-Null
      }
    } catch {
      continue
    }
  }
  return $names
}

function Get-LatestBatchSummary {
  param([string]$RepoRoot)
  $root = Join-Path $RepoRoot "assault_sim\session\reports\experiments"
  if (-not (Test-Path -Path $root -PathType Container)) { return $null }
  $summaries = @(
    Get-ChildItem -Path $root -Recurse -File -Filter "batch_summary.json" -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending
  )
  if ($summaries.Count -lt 1) { return $null }
  try {
    $arr = Get-Content -Path $summaries[0].FullName -Raw | ConvertFrom-Json
    if ($arr -isnot [System.Collections.IEnumerable]) { $arr = @($arr) }
    $success = @($arr | Where-Object { [string]$_.status -eq "success" }).Count
    $failed = @($arr | Where-Object { [string]$_.status -eq "failed" }).Count
    $skipped = @($arr | Where-Object { [string]$_.status -like "skipped_*" }).Count
    return [pscustomobject]@{
      path = $summaries[0].FullName
      success = $success
      failed = $failed
      skipped = $skipped
      total = @($arr).Count
    }
  } catch {
    return $null
  }
}

function Get-RunningExperiments {
  param([string]$RepoRoot)
  $root = Join-Path $RepoRoot "assault_sim\session\reports\experiments"
  $items = New-Object System.Collections.Generic.List[object]
  if (-not (Test-Path -Path $root -PathType Container)) { return $items }
  $results = @(
    Get-ChildItem -Path $root -Recurse -File -Filter "result.json" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -notmatch "\\batch_" } |
      Sort-Object LastWriteTime -Descending
  )
  foreach ($r in $results) {
    try {
      $obj = Get-Content -Path $r.FullName -Raw | ConvertFrom-Json
      if ([string]$obj.status -eq "running") {
        $items.Add([pscustomobject]@{
          experiment_id = [string]$obj.experiment_id
          run_dir = [string]$obj.run_dir
          started_at_utc = [string]$obj.started_at_utc
        }) | Out-Null
      }
    } catch {
      continue
    }
  }
  return $items
}

if (Test-Path -Path $lockPath -PathType Leaf) {
  try {
    $lock = Get-Content -Path $lockPath -Raw | ConvertFrom-Json
    throw ("Queue worker already running (pid={0}). Remove lock if stale: {1}" -f $lock.pid, $lockPath)
  }
  catch {
    throw ("Queue worker lock exists: {0}. Remove if stale." -f $lockPath)
  }
}

try {
  $lockPayload = [ordered]@{
    pid = $PID
    started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    manifests_dir = $ManifestsDir
  }
  ($lockPayload | ConvertTo-Json -Depth 4) | Out-File -FilePath $lockPath -Encoding UTF8

  $resolvedManifestsDir = Resolve-ManifestsPath -RepoRoot $RepoPath -DirPath $ManifestsDir
  Append-WorkerLog ("Queue worker started. manifests_dir={0}" -f $resolvedManifestsDir)

  while ($true) {
    $pending = Get-PendingManifestCount -DirPath $resolvedManifestsDir
    $pendingNames = @(Get-PendingManifestNames -DirPath $resolvedManifestsDir)
    $sample = @($pendingNames | Select-Object -First 5)
    Write-Heartbeat -State "idle" -Detail ("pending={0}" -f $pending) -Pending $pending -PendingSamples $sample

    $runningItems = @(Get-RunningExperiments -RepoRoot $RepoPath)
    if ($pending -gt 0) {
      if (-not $IgnoreRunningGuard -and $runningItems.Count -gt 0) {
        $runningSample = @($runningItems | Select-Object -First 3 | ForEach-Object { [string]$_.experiment_id })
        Append-WorkerLog ("Running experiment(s) detected ({0}). Waiting before launching new batch. Sample: {1}" -f $runningItems.Count, ($runningSample -join ", "))
        Write-Heartbeat -State "waiting_running_guard" -Detail ("running={0}" -f $runningItems.Count) -Pending $pending -PendingSamples $sample
        if ($Once) {
          break
        }
        Start-Sleep -Seconds $PollSeconds
        continue
      }
      Append-WorkerLog ("Pending manifests detected: {0}. Sample: {1}" -f $pending, (($sample -join ", ")))
      Write-Heartbeat -State "running_batch" -Detail ("pending={0}" -f $pending) -Pending $pending -PendingSamples $sample

      $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $batchScript,
        "-RepoPath", $RepoPath,
        "-ManifestsDir", $ManifestsDir,
        "-SkipCompleted",
        "-UpdateManifestStatus",
        "-ContinueOnError"
      )
      if ($ApplyChanges) {
        $args += "-ApplyChanges"
      }
      if ($ForceOldMismatch) {
        $args += "-ForceOldMismatch"
      }
      $output = @()
      $exitCode = 0
      try {
        $output = & powershell @args 2>&1
        $exitCode = $LASTEXITCODE
      }
      catch {
        $output = @($_ | Out-String)
        $exitCode = 1
      }
      $output | Out-File -FilePath $workerLogPath -Append -Encoding UTF8

      if ($exitCode -eq 0) {
        Append-WorkerLog "Batch execution completed."
      } else {
        Append-WorkerLog ("Batch execution finished with errors (exit={0})." -f $exitCode)
      }
      $latest = Get-LatestBatchSummary -RepoRoot $RepoPath
      if ($latest -ne $null) {
        Append-WorkerLog ("Latest batch summary: total={0} success={1} failed={2} skipped={3} file={4}" -f $latest.total, $latest.success, $latest.failed, $latest.skipped, $latest.path)
        Write-Heartbeat -State "batch_done" -Detail ("success={0} failed={1} skipped={2}" -f $latest.success, $latest.failed, $latest.skipped) -Pending 0 -PendingSamples @()
      }
    } else {
      Append-WorkerLog "No pending manifests."
    }

    if ($Once) {
      Write-Heartbeat -State "done_once" -Detail "completed single cycle"
      break
    }

    Start-Sleep -Seconds $PollSeconds
  }
}
finally {
  Write-Heartbeat -State "stopped" -Detail "worker exiting"
  if (Test-Path -Path $lockPath -PathType Leaf) {
    Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
  }
  Append-WorkerLog "Queue worker stopped."
}

