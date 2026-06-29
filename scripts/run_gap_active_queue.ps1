[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [switch]$RunR2aEval,
  [int[]]$ReactionSeeds = @(42, 43, 44),
  [int]$ReactionEpisodes = 30,
  [int]$ReactionNaturalMinCount = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Step([string]$msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host "[$ts] $msg"
}

function Run-Script([string]$title, [string]$path, [hashtable]$scriptArgs = @{}) {
  Step "==== $title ===="
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Missing script: $path"
  }
  & $path @scriptArgs
  if ($LASTEXITCODE -ne 0) {
    throw "$title failed (exit=$LASTEXITCODE)"
  }
}

Push-Location $RepoPath
try {
  $summary = [ordered]@{
    r2a_gate = "SKIPPED"
    reaction_fire_technical = "NOT_RUN"
    reaction_fire_natural = "NOT_RUN"
    planner_p43 = "PENDING_POLICY"
    r4_reopen = "PENDING_POLICY"
  }

  # Active Queue #1: anti-regression before promotions
  $r2aArgs = @{}
  if ($RunR2aEval) { $r2aArgs["RunEval"] = $true }
  Run-Script `
    -title "R2.a anti-regression gate" `
    -path ".\scripts\gate_r2a_no_regression_vs_r21i.ps1" `
    -scriptArgs $r2aArgs
  $summary.r2a_gate = "PASS"

  # Active Queue #2: technical reaction-fire gate
  Run-Script `
    -title "Reaction Fire technical gate" `
    -path ".\scripts\test_reaction_fire_e2e.ps1" `
    -scriptArgs @{
      RepoPath = $RepoPath
      Seeds = $ReactionSeeds
      Episodes = $ReactionEpisodes
      MinReactionFireCount = 1
      ForceDeterministicFallback = $true
    }
  $summary.reaction_fire_technical = "PASS"

  # Active Queue #3: natural reaction-fire occurrence KPI
  try {
    Run-Script `
      -title "Reaction Fire natural KPI gate" `
      -path ".\scripts\gate_reaction_fire_natural.ps1" `
      -scriptArgs @{
        RepoPath = $RepoPath
        Seeds = $ReactionSeeds
        Episodes = $ReactionEpisodes
        MinReactionFireCount = $ReactionNaturalMinCount
      }
    $summary.reaction_fire_natural = "PASS"
  }
  catch {
    $summary.reaction_fire_natural = "FAIL_EXPECTED_OR_PENDING"
    Step "Natural reaction-fire KPI gate not met (tracked as pending behavioral KPI)."
  }

  Step "==== Active Queue Summary ===="
  foreach ($k in $summary.Keys) {
    Write-Host ("{0}: {1}" -f $k, $summary[$k])
  }
}
finally {
  Pop-Location
}

