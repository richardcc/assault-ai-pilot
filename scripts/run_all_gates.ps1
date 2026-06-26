param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$SmokeEpisodes = 10
)

$ErrorActionPreference = "Stop"

Write-Host "===== GATE 1: Tests ====="
& (Join-Path $Repo "scripts\gate_tests.ps1") -Repo $Repo

Write-Host "===== GATE 2: Smoke Eval ====="
& (Join-Path $Repo "scripts\gate_smoke_eval.ps1") -Repo $Repo -Episodes $SmokeEpisodes -DedupScenarioSchedule

Write-Host "===== GATE 3: FPS Smoke ====="
& (Join-Path $Repo "scripts\gate_fps_smoke.ps1") -Repo $Repo