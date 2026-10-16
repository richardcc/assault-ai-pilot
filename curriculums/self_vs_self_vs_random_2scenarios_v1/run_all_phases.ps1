param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$CurriculumYaml = ".\curriculums\self_vs_self_vs_random_2scenarios_v1\curriculum.yaml",
  [string]$StartPhase = "",
  [switch]$ContinueFromLatestCheckpoint,
  [switch]$AllowPhase1Resume,
  [switch]$StopOnGateFail,
  [switch]$StopOnPhaseError,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$delegate = Join-Path $PSScriptRoot "..\self_vs_self_vs_random_v1\run_all_phases.ps1"
if (-not (Test-Path $delegate)) {
  throw "Missing delegate script: $delegate"
}

$invokeParams = @{
  Repo = $Repo
  CurriculumYaml = $CurriculumYaml
}
if (-not [string]::IsNullOrWhiteSpace($StartPhase)) {
  $invokeParams["StartPhase"] = $StartPhase
}
if ($ContinueFromLatestCheckpoint) { $invokeParams["ContinueFromLatestCheckpoint"] = $true }
if ($AllowPhase1Resume) { $invokeParams["AllowPhase1Resume"] = $true }
if ($StopOnGateFail) { $invokeParams["StopOnGateFail"] = $true }
if ($StopOnPhaseError) { $invokeParams["StopOnPhaseError"] = $true }
if ($DryRun) { $invokeParams["DryRun"] = $true }

& $delegate @invokeParams
