param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$Episodes = 10
)

Set-Location $Repo
.\.venv\Scripts\Activate.ps1

$modelPath = Join-Path $Repo "models\scenario_battaglia_cittadina_2_1\side_US\sb3_latest_US.zip"
if (-not (Test-Path $modelPath)) {
  Write-Host "[BLOCKED] Missing model artifact:"
  Write-Host "  $modelPath"
  Write-Host "Run/finish training first, then re-run this script."
  exit 1
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $Repo "smoke_eval_multiseed_$ts.log"

foreach ($seed in 42, 43, 44) {
  Write-Host ""
  Write-Host "=== EVAL seed=$seed episodes=$Episodes ==="
  python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed $seed 2>&1 | Tee-Object -FilePath $log -Append
}

Write-Host ""
Write-Host "[DONE] Multi-seed smoke completed. Log:"
Write-Host "  $log"
