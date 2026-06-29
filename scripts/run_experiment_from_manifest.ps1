[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$ManifestPath,
  [string]$RepoPath = "C:\repos\python\assault",
  [switch]$SkipTrain,
  [switch]$SkipGate,
  [switch]$ApplyChanges,
  [switch]$ForceOldMismatch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath does not exist: $RepoPath"
}

$manifestFullPath = $ManifestPath
if (-not [System.IO.Path]::IsPathRooted($manifestFullPath)) {
  $manifestFullPath = Join-Path $RepoPath $ManifestPath
}
if (-not (Test-Path -Path $manifestFullPath -PathType Leaf)) {
  throw "Manifest file does not exist: $manifestFullPath"
}

$python = Join-Path $RepoPath ".venv\Scripts\python.exe"
if (-not (Test-Path -Path $python -PathType Leaf)) {
  throw "Python venv not found: $python"
}
$validatorScript = Join-Path $RepoPath "scripts\validate_experiment_manifest.py"
if (-not (Test-Path -Path $validatorScript -PathType Leaf)) {
  throw "Validator script not found: $validatorScript"
}
$applierScript = Join-Path $RepoPath "scripts\apply_experiment_changes.py"
if (-not (Test-Path -Path $applierScript -PathType Leaf)) {
  throw "Applier script not found: $applierScript"
}

function Get-ManifestChangedFiles {
  param(
    [object]$ManifestObject,
    [string]$RepoRoot
  )
  $files = New-Object System.Collections.Generic.List[string]
  foreach ($c in @($ManifestObject.changes)) {
    try {
      $rel = [string]$c.file
      if ([string]::IsNullOrWhiteSpace($rel)) { continue }
      $full = $rel
      if (-not [System.IO.Path]::IsPathRooted($full)) {
        $full = Join-Path $RepoRoot $rel
      }
      $norm = (Resolve-Path -Path $full -ErrorAction Stop).Path
      if (-not $files.Contains($norm)) {
        $files.Add($norm) | Out-Null
      }
    } catch {
      continue
    }
  }
  return $files
}

function Restore-Backups {
  param([hashtable]$Backups)
  foreach ($k in $Backups.Keys) {
    $src = [string]$Backups[$k]
    $dst = [string]$k
    if ((Test-Path -Path $src -PathType Leaf)) {
      Copy-Item -Path $src -Destination $dst -Force
    }
  }
}

Push-Location $RepoPath
try {
  Write-Host ("Validating manifest: {0}" -f $manifestFullPath)
  & $python $validatorScript $manifestFullPath
  if ($LASTEXITCODE -ne 0) {
    throw ("Manifest validation failed with exit code {0}" -f $LASTEXITCODE)
  }

  $manifest = Get-Content -Path $manifestFullPath -Raw | ConvertFrom-Json
  $experimentId = [string]$manifest.experiment_id
  if ([string]::IsNullOrWhiteSpace($experimentId)) {
    throw "experiment_id is empty after validation."
  }

  $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runDir = Join-Path $RepoPath ("assault_sim\session\reports\experiments\{0}_{1}" -f $experimentId, $timestamp)
  New-Item -ItemType Directory -Path $runDir -Force | Out-Null

  $manifestCopyPath = Join-Path $runDir "manifest.json"
  Copy-Item -Path $manifestFullPath -Destination $manifestCopyPath -Force

  $trainCommand = [string]$manifest.execution.train_command
  $gateCommand = [string]$manifest.execution.gate_command

  $result = [ordered]@{
    experiment_id = $experimentId
    status = "running"
    run_dir = $runDir
    manifest = $manifestCopyPath
    skip_train = [bool]$SkipTrain
    skip_gate = [bool]$SkipGate
    train = @{
      command = $trainCommand
      executed = $false
      exit_code = $null
      log = (Join-Path $runDir "train.log")
    }
    gate = @{
      command = $gateCommand
      executed = $false
      exit_code = $null
      log = (Join-Path $runDir "gate.log")
    }
    started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    finished_at_utc = $null
  }
  $resultPath = Join-Path $runDir "result.json"
  ($result | ConvertTo-Json -Depth 8) | Out-File -FilePath $resultPath -Encoding UTF8

  $backups = @{}

  if ($ApplyChanges) {
    $backupDir = Join-Path $runDir "backup_before_apply"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $changedFiles = Get-ManifestChangedFiles -ManifestObject $manifest -RepoRoot $RepoPath
    foreach ($f in $changedFiles) {
      $name = [System.IO.Path]::GetFileName($f)
      $safe = "{0}_{1}" -f ([System.IO.Path]::GetFileNameWithoutExtension($name)), ([System.IO.Path]::GetExtension($name).TrimStart('.'))
      $backupPath = Join-Path $backupDir ($safe + ".bak")
      Copy-Item -Path $f -Destination $backupPath -Force
      $backups[$f] = $backupPath
    }
    Write-Host ("[APPLY] applying manifest changes")
    $applyArgs = @($applierScript, "--repo-root", $RepoPath, "--manifest", $manifestFullPath)
    if ($ForceOldMismatch) {
      $applyArgs += "--force-old-mismatch"
    }
    & $python @applyArgs
    if ($LASTEXITCODE -ne 0) {
      Restore-Backups -Backups $backups
      $result.status = "apply_failed"
      $result.finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
      ($result | ConvertTo-Json -Depth 8) | Out-File -FilePath $resultPath -Encoding UTF8
      throw ("Apply changes failed with exit code {0}" -f $LASTEXITCODE)
    }
  }

  if (-not $SkipTrain) {
    Write-Host ("[TRAIN] {0}" -f $trainCommand)
    $result.train.executed = $true
    & powershell -NoProfile -ExecutionPolicy Bypass -Command $trainCommand 2>&1 | Tee-Object -FilePath $result.train.log
    $result.train.exit_code = $LASTEXITCODE
    if ($result.train.exit_code -ne 0) {
      if ($ApplyChanges) {
        Restore-Backups -Backups $backups
      }
      $result.status = "train_failed"
      $result.finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
      ($result | ConvertTo-Json -Depth 8) | Out-File -FilePath $resultPath -Encoding UTF8
      throw ("Training command failed with exit code {0}" -f $result.train.exit_code)
    }
  }

  if (-not $SkipGate) {
    Write-Host ("[GATE] {0}" -f $gateCommand)
    $result.gate.executed = $true
    & powershell -NoProfile -ExecutionPolicy Bypass -Command $gateCommand 2>&1 | Tee-Object -FilePath $result.gate.log
    $result.gate.exit_code = $LASTEXITCODE
    if ($result.gate.exit_code -ne 0) {
      if ($ApplyChanges) {
        Restore-Backups -Backups $backups
      }
      $result.status = "gate_failed"
      $result.finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
      ($result | ConvertTo-Json -Depth 8) | Out-File -FilePath $resultPath -Encoding UTF8
      throw ("Gate command failed with exit code {0}" -f $result.gate.exit_code)
    }
  }

  $result.status = "success"
  $result.finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  ($result | ConvertTo-Json -Depth 8) | Out-File -FilePath $resultPath -Encoding UTF8

  Write-Host ""
  Write-Host ("Experiment completed: {0}" -f $experimentId)
  Write-Host ("Run dir: {0}" -f $runDir)
  Write-Host ("Result: {0}" -f $resultPath)
}
finally {
  Pop-Location
}

