<#
.SYNOPSIS
Performs safe archive cleanup batch (dry-run by default).

.DESCRIPTION
Collects low-risk cleanup candidates (backup train configs and obsolete tmp_parallel configs)
and either prints them (dry-run) or moves them to a timestamped archive directory.

.PARAMETER RepoPath
Repository root path.

.PARAMETER Apply
If set, move files to archive. Without this switch, script runs in dry-run mode.

.EXAMPLE
.\scripts\archive_cleanup_batch1.ps1

.EXAMPLE
.\scripts\archive_cleanup_batch1.ps1 -Apply
#>
[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "Repo path not found: $RepoPath"
}

$archiveRoot = Join-Path $RepoPath ("assault_sim\deprecated\cleanup_batch1_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$targets = New-Object System.Collections.Generic.List[string]

# Group 1: backup train configs.
$targets.Add((Join-Path $RepoPath "assault_sim\config\train_config.backup.json")) | Out-Null
$targets.Add((Join-Path $RepoPath "assault_sim\config\train_config.ab_backup.json")) | Out-Null
$targets.Add((Join-Path $RepoPath "assault_sim\config\train_config.c2_backup.json")) | Out-Null
$targets.Add((Join-Path $RepoPath "assault_sim\config\train_config.curriculum_backup.json")) | Out-Null

# Group 2: old tmp parallel configs (keep trainer_sweep and current scenario-side base configs).
$tmpParallel = Join-Path $RepoPath "assault_sim\session\tmp_parallel"
if (Test-Path -Path $tmpParallel -PathType Container) {
  $tmpFiles = Get-ChildItem -Path $tmpParallel -File -Filter "*.json"
  foreach ($f in $tmpFiles) {
    $name = [string]$f.Name
    if ($name -match "trainer_sweep") { continue }
    if ($name -match "battaglia_cittadina_2_1_(it|us)\.parallel\.json") { continue }
    if ($name -match "mettete_i_piedi_terra_1_(us|ge)\.parallel\.json") { continue }
    $targets.Add($f.FullName) | Out-Null
  }
}

$existing = @($targets | Where-Object { Test-Path -Path $_ -PathType Leaf } | Sort-Object -Unique)

Write-Host ""
Write-Host "=== Cleanup Batch 1 (Safe Archive) ==="
Write-Host ("Mode: {0}" -f $(if ($Apply) { "APPLY (move files)" } else { "DRY-RUN (no changes)" }))
Write-Host ("Candidates found: {0}" -f $existing.Count)
$existing | ForEach-Object { Write-Host (" - {0}" -f $_) }

if (-not $Apply) {
  Write-Host ""
  Write-Host "Dry-run complete. Re-run with -Apply to move files to:"
  Write-Host ("  {0}" -f $archiveRoot)
  exit 0
}

New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null

foreach ($src in $existing) {
  $rel = $src.Substring($RepoPath.Length).TrimStart('\', '/')
  $dst = Join-Path $archiveRoot $rel
  $dstDir = Split-Path -Path $dst -Parent
  New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
  Move-Item -Path $src -Destination $dst -Force
}

Write-Host ""
Write-Host ("Archived {0} files to: {1}" -f $existing.Count, $archiveRoot)
