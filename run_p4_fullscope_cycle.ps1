param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$EvalEpisodes = 50,
  [string]$SnapshotTag = "p4_fullscope",
  [string]$BaselineSnapshot = ""
)

$ErrorActionPreference = "Stop"
Set-Location $Repo
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

Write-Host "== P4 Fullscope cycle start =="
Write-Host "Repo: $Repo"
Write-Host "EvalEpisodes: $EvalEpisodes"
Write-Host "SnapshotTag: $SnapshotTag"
Write-Host ""

Remove-Item Env:ASSAULT_PERF_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:ASSAULT_PERF_EVERY -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONUNBUFFERED -ErrorAction SilentlyContinue

Write-Host "== TRAIN =="
python -m assault_sim.train.train_sb3

Write-Host ""
Write-Host "== STRICT EVAL (42/43/44) =="
powershell -ExecutionPolicy Bypass -File ".\run_eval_multiseed_strict.ps1" -Repo $Repo -Episodes $EvalEpisodes -Tag $SnapshotTag

if ($BaselineSnapshot) {
  $snapshotsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval\snapshots"
  $latest = Get-ChildItem $snapshotsDir -Filter "p4_snapshot_${SnapshotTag}_*.json" | Sort-Object LastWriteTime | Select-Object -Last 1
  if ($latest) {
    Write-Host ""
    Write-Host "== A/B COMPARE =="
    powershell -ExecutionPolicy Bypass -File ".\compare_p4_snapshots.ps1" -BaselineSnapshot $BaselineSnapshot -CandidateSnapshot $latest.FullName
  }
}

Write-Host ""
Write-Host "== P4 Fullscope cycle end =="
