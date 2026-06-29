[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int]$RefreshSeconds = 3,
  [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath does not exist: $RepoPath"
}

$experimentsRoot = Join-Path $RepoPath "assault_sim\session\reports\experiments"

function Get-DirStatus {
  param([string]$DirPath)

  $name = [System.IO.Path]::GetFileName($DirPath)
  $resultPath = Join-Path $DirPath "result.json"

  if (Test-Path -Path $resultPath -PathType Leaf) {
    try {
      $obj = Get-Content -Path $resultPath -Raw | ConvertFrom-Json
      $status = [string]($obj.status)
      if ([string]::IsNullOrWhiteSpace($status)) { $status = "unknown" }
      return [pscustomobject]@{
        name = $name
        type = "experiment"
        status = $status.ToUpperInvariant()
        started_at = [string]($obj.started_at_utc)
        finished_at = [string]($obj.finished_at_utc)
        path = $DirPath
      }
    }
    catch {
      return [pscustomobject]@{
        name = $name
        type = "experiment"
        status = "RESULT_PARSE_ERROR"
        started_at = ""
        finished_at = ""
        path = $DirPath
      }
    }
  }

  # Heuristic: if logs exist but no result yet, likely running/incomplete.
  $hasTrainLog = Test-Path -Path (Join-Path $DirPath "train.log") -PathType Leaf
  $hasGateLog = Test-Path -Path (Join-Path $DirPath "gate.log") -PathType Leaf
  $status = if ($hasTrainLog -or $hasGateLog) { "RUNNING_OR_INCOMPLETE" } else { "NO_RESULT" }
  return [pscustomobject]@{
    name = $name
    type = "experiment"
    status = $status
    started_at = ""
    finished_at = ""
    path = $DirPath
  }
}

function Get-BatchStatus {
  param([string]$DirPath)

  $name = [System.IO.Path]::GetFileName($DirPath)
  $summaryPath = Join-Path $DirPath "batch_summary.json"
  if (-not (Test-Path -Path $summaryPath -PathType Leaf)) {
    return [pscustomobject]@{
      name = $name
      type = "batch"
      status = "NO_SUMMARY"
      success = 0
      failed = 0
      path = $DirPath
    }
  }

  try {
    $arr = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
    if ($arr -isnot [System.Collections.IEnumerable]) {
      $arr = @($arr)
    }
    $ok = @($arr | Where-Object { [string]$_.status -eq "success" }).Count
    $fail = @($arr | Where-Object { [string]$_.status -ne "success" }).Count
    $status = if ($fail -gt 0) { "FAILED" } else { "SUCCESS" }
    return [pscustomobject]@{
      name = $name
      type = "batch"
      status = $status
      success = $ok
      failed = $fail
      path = $DirPath
    }
  }
  catch {
    return [pscustomobject]@{
      name = $name
      type = "batch"
      status = "SUMMARY_PARSE_ERROR"
      success = 0
      failed = 0
      path = $DirPath
    }
  }
}

function Render-View {
  param([string]$RootPath)

  Clear-Host
  Write-Host ("Experiment watch @ {0}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"))
  Write-Host ("Root: {0}" -f $RootPath)
  Write-Host ""

  if (-not (Test-Path -Path $RootPath -PathType Container)) {
    Write-Host "No experiments directory yet."
    return
  }

  $dirs = @(Get-ChildItem -Path $RootPath -Directory -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending)

  if ($dirs.Count -lt 1) {
    Write-Host "No experiment/batch runs found."
    return
  }

  $expRows = New-Object System.Collections.Generic.List[object]
  $batchRows = New-Object System.Collections.Generic.List[object]

  foreach ($d in $dirs) {
    if ($d.Name -like "batch_*") {
      $batchRows.Add((Get-BatchStatus -DirPath $d.FullName)) | Out-Null
    } elseif ($d.Name -eq "worker") {
      # Service runtime folder, not an experiment run folder.
      continue
    } else {
      $expRows.Add((Get-DirStatus -DirPath $d.FullName)) | Out-Null
    }
  }

  if ($expRows.Count -gt 0) {
    Write-Host "Experiments:"
    $expRows |
      Select-Object -First 15 |
      Format-Table name, status, started_at, finished_at -AutoSize
    Write-Host ""
  }

  if ($batchRows.Count -gt 0) {
    Write-Host "Batches:"
    $batchRows |
      Select-Object -First 10 |
      Format-Table name, status, success, failed -AutoSize
    Write-Host ""
  }

  Write-Host "Tip: open run folder to inspect train.log / gate.log / result.json"
}

if ($Once) {
  Render-View -RootPath $experimentsRoot
  exit 0
}

while ($true) {
  Render-View -RootPath $experimentsRoot
  Start-Sleep -Seconds ([Math]::Max(1, $RefreshSeconds))
}

