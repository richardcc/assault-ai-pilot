param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [int]$Seed = 42
)

$ErrorActionPreference = "Stop"

$baseScript = Join-Path $Repo "scripts\run_r4_policy_redesign_gate.ps1"
if (-not (Test-Path -Path $baseScript -PathType Leaf)) {
  throw "No existe script base R4: $baseScript"
}

Write-Host "=== R4.1 (step-in head) gate ===" -ForegroundColor Cyan
Write-Host "Single lever: explicit legal step-in head"
Write-Host "Repo: $Repo"
Write-Host "Side/Scenario: $Side / $Scenario"
Write-Host "Seed: $Seed"

& $baseScript `
  -Repo $Repo `
  -Side $Side `
  -Scenario $Scenario `
  -Seed $Seed `
  -MicroEpisodes 20 `
  -FullEpisodes 120 `
  -TargetStepinSelectionRate 0.50 `
  -KillMinSelectionRate 0.35 `
  -KillMaxVpEntryMissedRate 0.92

exit $LASTEXITCODE
