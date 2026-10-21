param(
  [string]$Checkpoint = "C:\repos\python\assault\runs\efficientzero_v2_789eb453\checkpoints\final.pt",
  [switch]$DryRun
)

$Repo = "C:\repos\python\assault"
Set-Location $Repo

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " [VP Acceleration] Relanzando Fase 5 (Urban Assault Puro) " -ForegroundColor Yellow
Write-Host "  Checkpoint: $Checkpoint" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

$params = @(
  "-ExecutionPolicy", "Bypass",
  "-File", ".\curriculums\common\run_dynamic_gated_curriculum.ps1",
  "-CurriculumYaml", ".\curriculums\vp_acceleration\curriculum.yaml",
  "-StartPhase", "phase5_urban_assault_pure_offensive",
  "-ExplicitStartCheckpoint", $Checkpoint
)
if ($DryRun) { $params += "-DryRun" }

powershell.exe @params
