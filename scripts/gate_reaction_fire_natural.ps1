[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int[]]$Seeds = @(42, 43, 44),
  [int]$Episodes = 30,
  [int]$MinReactionFireCount = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $RepoPath "scripts\test_reaction_fire_e2e.ps1"
if (-not (Test-Path -LiteralPath $scriptPath)) {
  throw "Missing script: $scriptPath"
}

Write-Host "[gate_reaction_fire_natural] Running natural-occurrence gate (no deterministic fallback)..."
$argsMap = @{
  RepoPath = $RepoPath
  Seeds = $Seeds
  Episodes = $Episodes
  MinReactionFireCount = $MinReactionFireCount
}
& $scriptPath @argsMap

if ($LASTEXITCODE -ne 0) {
  throw "Natural reaction-fire gate failed (exit=$LASTEXITCODE)"
}

Write-Host "[gate_reaction_fire_natural] PASS"

