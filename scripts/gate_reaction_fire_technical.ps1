[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int[]]$Seeds = @(42, 43, 44),
  [int]$Episodes = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $RepoPath "scripts\test_reaction_fire_e2e.ps1"
if (-not (Test-Path -LiteralPath $scriptPath)) {
  throw "Missing script: $scriptPath"
}

Write-Host "[gate_reaction_fire_technical] Running technical integration gate (deterministic fallback ON)..."
& $scriptPath `
  -RepoPath $RepoPath `
  -Seeds $Seeds `
  -Episodes $Episodes `
  -MinReactionFireCount 1 `
  -ForceDeterministicFallback

if ($LASTEXITCODE -ne 0) {
  throw "Technical reaction-fire gate failed (exit=$LASTEXITCODE)"
}

Write-Host "[gate_reaction_fire_technical] PASS"

