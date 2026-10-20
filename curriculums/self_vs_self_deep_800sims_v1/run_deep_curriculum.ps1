param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$StartPhase = "",
  [string]$ExplicitStartCheckpoint = "",
  [switch]$ContinueFromLatestCheckpoint,
  [switch]$WaitForActiveCurriculum,
  [switch]$StopOnGateFail,
  [switch]$StopOnPhaseError,
  [int]$DefaultMaxReinforcementCycles = 3,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($WaitForActiveCurriculum) {
  Write-Host "Waiting for active background curriculum execution to finish..." -ForegroundColor Cyan
  while ($true) {
    # Check if any python training process or runner is active
    $activeTrainers = @(Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
      $_.MainWindowTitle -like "*train*" -or $_.CommandLine -like "*train_efficientzero_v2*"
    })
    # Also check if curriculum powershell runs
    $activeRunners = @(Get-Process -Name "powershell", "pwsh" -ErrorAction SilentlyContinue | Where-Object {
      $_.CommandLine -like "*run_all_phases.ps1*" -and $_.Id -ne $PID
    })
    if ($activeRunners.Count -eq 0 -and $activeTrainers.Count -eq 0) {
      Write-Host "No active curriculum processes detected. Proceeding to launch deep curriculum!" -ForegroundColor Green
      break
    }
    Write-Host ("Waiting for active background processes ({0} trainer, {1} runner)... Sleeping 30s." -f $activeTrainers.Count, $activeRunners.Count) -ForegroundColor Gray
    Start-Sleep -Seconds 30
  }
}

$curriculumYaml = Join-Path $PSScriptRoot "curriculum.yaml"
$delegate = Join-Path $Repo "curriculums\common\run_dynamic_gated_curriculum.ps1"

if (-not (Test-Path $delegate)) {
  throw "Missing dynamic gated curriculum engine: $delegate"
}

$invokeParams = @{
  Repo = $Repo
  CurriculumYaml = $curriculumYaml
  DefaultMaxReinforcementCycles = $DefaultMaxReinforcementCycles
}

if (-not [string]::IsNullOrWhiteSpace($StartPhase)) {
  $invokeParams["StartPhase"] = $StartPhase
}

if (-not [string]::IsNullOrWhiteSpace($ExplicitStartCheckpoint)) {
  $invokeParams["ExplicitStartCheckpoint"] = $ExplicitStartCheckpoint
}

if ($ContinueFromLatestCheckpoint) {
  $invokeParams["ContinueFromLatestCheckpoint"] = $true
}

if ($StopOnGateFail) {
  $invokeParams["StopOnGateFail"] = $true
}

if ($StopOnPhaseError) {
  $invokeParams["StopOnPhaseError"] = $true
}

if ($DryRun) {
  $invokeParams["DryRun"] = $true
}

& $delegate @invokeParams
