[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [string]$ManifestsDir = ".\scripts\experiments",
  [string[]]$FromStatus = @("done_revert"),
  [string]$ToStatus = "planned",
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath does not exist: $RepoPath"
}

if ([string]::IsNullOrWhiteSpace($ToStatus)) {
  throw "ToStatus must be a non-empty string."
}

$resolvedManifestsDir = $ManifestsDir
if (-not [System.IO.Path]::IsPathRooted($resolvedManifestsDir)) {
  $resolvedManifestsDir = Join-Path $RepoPath $ManifestsDir
}
if (-not (Test-Path -Path $resolvedManifestsDir -PathType Container)) {
  throw "ManifestsDir does not exist: $resolvedManifestsDir"
}

$fromSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($s in $FromStatus) {
  if (-not [string]::IsNullOrWhiteSpace($s)) {
    [void]$fromSet.Add($s.Trim())
  }
}
if ($fromSet.Count -lt 1) {
  throw "FromStatus cannot be empty."
}

$files = @(
  Get-ChildItem -Path $resolvedManifestsDir -Filter "*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object Name
)

if ($files.Count -lt 1) {
  throw "No manifest files found in: $resolvedManifestsDir"
}

$rows = New-Object System.Collections.Generic.List[object]
$changedCount = 0

foreach ($f in $files) {
  try {
    $obj = Get-Content -Path $f.FullName -Raw | ConvertFrom-Json
  }
  catch {
    $rows.Add([pscustomobject]@{
      manifest = $f.Name
      experiment_id = ""
      old_status = "PARSE_ERROR"
      new_status = ""
      changed = $false
    }) | Out-Null
    continue
  }

  $oldStatus = [string]$obj.status
  if ([string]::IsNullOrWhiteSpace($oldStatus)) {
    $oldStatus = ""
  }

  $shouldChange = $fromSet.Contains($oldStatus)
  if ($shouldChange) {
    if (-not $DryRun) {
      $obj.status = $ToStatus
      ($obj | ConvertTo-Json -Depth 12) | Out-File -FilePath $f.FullName -Encoding UTF8
    }
    $changedCount += 1
  }

  $rows.Add([pscustomobject]@{
    manifest = $f.Name
    experiment_id = [string]$obj.experiment_id
    old_status = $oldStatus
    new_status = if ($shouldChange) { $ToStatus } else { $oldStatus }
    changed = $shouldChange
  }) | Out-Null
}

Write-Host ""
Write-Host ("Manifest dir: {0}" -f $resolvedManifestsDir)
Write-Host ("Mode: {0}" -f ($(if ($DryRun) { "DRY-RUN" } else { "APPLY" })))
Write-Host ("FromStatus: {0}" -f (($FromStatus -join ", ")))
Write-Host ("ToStatus: {0}" -f $ToStatus)
Write-Host ""

$rows | Format-Table manifest, experiment_id, old_status, new_status, changed -AutoSize

Write-Host ""
if ($DryRun) {
  Write-Host ("Would change: {0}" -f $changedCount)
} else {
  Write-Host ("Changed: {0}" -f $changedCount)
}

