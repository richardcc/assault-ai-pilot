param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$Episodes = 50,
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [string]$CandidateTag = "p4_candidate",
  [string]$BaselineSnapshot = ""
)

$ErrorActionPreference = "Stop"
Set-Location $Repo
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

$snapshotsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval\snapshots"
New-Item -ItemType Directory -Path $snapshotsDir -Force | Out-Null

if ([string]::IsNullOrWhiteSpace($BaselineSnapshot)) {
  $baselineCandidate = Get-ChildItem $snapshotsDir -Filter "p4_snapshot_*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($baselineCandidate) {
    $BaselineSnapshot = $baselineCandidate.FullName
  }
}

Write-Host "== P4 post-train pack =="
Write-Host "Repo: $Repo"
Write-Host "Episodes: $Episodes"
Write-Host "Side/Scenario: $Side / $Scenario"
if ($BaselineSnapshot) {
  Write-Host "Baseline snapshot: $BaselineSnapshot"
} else {
  Write-Host "Baseline snapshot: (none; compare will be skipped)"
}
Write-Host ""

Write-Host "== STRICT EVAL + SNAPSHOT =="
& powershell -ExecutionPolicy Bypass -File ".\run_eval_multiseed_strict.ps1" `
  -Repo $Repo `
  -Episodes $Episodes `
  -Side $Side `
  -Scenario $Scenario `
  -Tag $CandidateTag

$candidate = Get-ChildItem $snapshotsDir -Filter "p4_snapshot_${CandidateTag}_*.json" -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if (-not $candidate) {
  throw "Candidate snapshot not found for tag: $CandidateTag"
}

Write-Host ""
Write-Host ("Candidate snapshot: {0}" -f $candidate.FullName)

if ($BaselineSnapshot -and (Test-Path $BaselineSnapshot)) {
  Write-Host ""
  Write-Host "== A/B COMPARE =="
  & powershell -ExecutionPolicy Bypass -File ".\compare_p4_snapshots.ps1" `
    -BaselineSnapshot $BaselineSnapshot `
    -CandidateSnapshot $candidate.FullName
} else {
  Write-Host ""
  Write-Host "A/B compare skipped (no valid baseline snapshot provided/found)."
}

Write-Host ""
Write-Host "== DONE =="
