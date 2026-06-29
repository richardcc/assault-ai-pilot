[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$ManifestPath,
  [string]$RepoPath = "C:\repos\python\assault",
  [switch]$AllowWithoutSuccessResult
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

$activeDir = Join-Path $RepoPath "scripts\experiments"
$archivePassedDir = Join-Path $RepoPath "scripts\experiments_archive\passed"
New-Item -ItemType Directory -Path $archivePassedDir -Force | Out-Null

function Read-JsonFile {
  param([string]$Path)
  return (Get-Content -Path $Path -Raw | ConvertFrom-Json)
}

function Write-JsonFile {
  param([string]$Path, [object]$Object)
  ($Object | ConvertTo-Json -Depth 12) | Out-File -FilePath $Path -Encoding UTF8
}

function Find-LatestSuccessResult {
  param(
    [string]$RepoRoot,
    [string]$ExperimentId
  )
  $root = Join-Path $RepoRoot "assault_sim\session\reports\experiments"
  if (-not (Test-Path -Path $root -PathType Container)) {
    return $null
  }
  $results = @(
    Get-ChildItem -Path $root -Recurse -File -Filter "result.json" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -notmatch "\\batch_" } |
      Sort-Object LastWriteTime -Descending
  )
  foreach ($r in $results) {
    try {
      $obj = Read-JsonFile -Path $r.FullName
      if ([string]$obj.experiment_id -eq $ExperimentId -and [string]$obj.status -eq "success") {
        return $r.FullName
      }
    }
    catch {
      continue
    }
  }
  return $null
}

$manifestObj = Read-JsonFile -Path $manifestFullPath
$experimentId = [string]$manifestObj.experiment_id
if ([string]::IsNullOrWhiteSpace($experimentId)) {
  throw "Manifest has no experiment_id: $manifestFullPath"
}

$successResultPath = Find-LatestSuccessResult -RepoRoot $RepoPath -ExperimentId $experimentId
if (-not $AllowWithoutSuccessResult -and -not $successResultPath) {
  throw ("No SUCCESS result found for experiment_id={0}. Use -AllowWithoutSuccessResult to override." -f $experimentId)
}

$manifestObj.status = "done_keep"
$manifestObj.promoted_at_utc = (Get-Date).ToUniversalTime().ToString("o")
if ($successResultPath) {
  $manifestObj.promoted_from_result = $successResultPath
}

$manifestName = [System.IO.Path]::GetFileName($manifestFullPath)
$targetPath = Join-Path $archivePassedDir $manifestName

Write-JsonFile -Path $targetPath -Object $manifestObj

if ((Resolve-Path $manifestFullPath).Path -ne (Resolve-Path $targetPath).Path) {
  Remove-Item -Path $manifestFullPath -Force
}

$promotionLogDir = Join-Path $RepoPath "assault_sim\session\reports\experiments\promotions"
New-Item -ItemType Directory -Path $promotionLogDir -Force | Out-Null
$promotionLogPath = Join-Path $promotionLogDir ("promotion_{0}_{1}.json" -f $experimentId, (Get-Date -Format "yyyyMMdd_HHmmss"))

$logObj = [ordered]@{
  experiment_id = $experimentId
  manifest_name = $manifestName
  source_manifest = $manifestFullPath
  archived_manifest = $targetPath
  status = "done_keep"
  success_result = $successResultPath
  promoted_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
Write-JsonFile -Path $promotionLogPath -Object $logObj

Write-Host ""
Write-Host ("Promoted experiment: {0}" -f $experimentId)
Write-Host ("Archived manifest: {0}" -f $targetPath)
Write-Host ("Promotion log: {0}" -f $promotionLogPath)

