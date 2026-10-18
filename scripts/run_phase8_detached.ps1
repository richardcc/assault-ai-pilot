$Repo = "C:\repos\python\assault"
Set-Location $Repo
$logPath = Join-Path $Repo "runs_curriculum\experiments\runner_detached.log"
$ckpt = "C:\repos\python\assault\runs_curriculum\efficientzero_v2_c5a64c93\checkpoints\final.pt"

& powershell.exe -ExecutionPolicy Bypass -File "$Repo\curriculums\common\run_dynamic_gated_curriculum.ps1" `
    -CurriculumYaml "$Repo\curriculums\self_vs_self_vs_random_2scenarios_v1\curriculum.yaml" `
    -StartPhase "phase6_self_only_stabilize" `
    -ExplicitStartCheckpoint $ckpt `
    -StopOnPhaseError *>&1 | Tee-Object -FilePath $logPath
