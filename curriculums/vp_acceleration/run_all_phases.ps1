param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$CurriculumYaml = ".\curriculums\vp_acceleration\curriculum.yaml",
  [string]$StartPhase = "",
  [switch]$ContinueFromLatestCheckpoint,
  [switch]$AllowPhase1Resume,
  [switch]$StopOnGateFail,
  [switch]$StopOnPhaseError,
  [int]$DefaultMaxReinforcementCycles = 3,
  [string]$ExplicitStartCheckpoint = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$delegate = Join-Path $PSScriptRoot "..\common\run_dynamic_gated_curriculum.ps1"
if (-not (Test-Path $delegate)) {
  $delegate = Join-Path $Repo "curriculums\common\run_dynamic_gated_curriculum.ps1"
}
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
if ($DefaultMaxReinforcementCycles) { $invokeParams["DefaultMaxReinforcementCycles"] = $DefaultMaxReinforcementCycles }
if (-not [string]::IsNullOrWhiteSpace($ExplicitStartCheckpoint)) {
  $invokeParams["ExplicitStartCheckpoint"] = $ExplicitStartCheckpoint
}
if ($DryRun) { $invokeParams["DryRun"] = $true }

& $delegate @invokeParams
