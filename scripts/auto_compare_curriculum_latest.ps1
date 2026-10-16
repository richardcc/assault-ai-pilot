param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaselineLog = "",
  [string]$CandidateLog = "",
  [string]$OutDir = ".\runs_curriculum\experiments\reporting",
  [switch]$CommonOnly,
  [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"

function Resolve-LatestEvalLog {
  param(
    [string]$RepoRoot,
    [string]$ExcludePath = ""
  )
  $root = Join-Path $RepoRoot "runs_curriculum\experiments\curriculum_cycles"
  if (-not (Test-Path $root)) { return $null }
  $items = Get-ChildItem -Path $root -Recurse -File -Filter "02_eval.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending
  foreach ($it in $items) {
    if ([string]::IsNullOrWhiteSpace($ExcludePath)) { return [string]$it.FullName }
    if ([string]::Equals([string]$it.FullName, [string]$ExcludePath, [System.StringComparison]::OrdinalIgnoreCase)) {
      continue
    }
    return [string]$it.FullName
  }
  return $null
}

Push-Location $Repo
try {
  if ([string]::IsNullOrWhiteSpace($CandidateLog)) {
    $CandidateLog = Resolve-LatestEvalLog -RepoRoot $Repo
  }
  if ([string]::IsNullOrWhiteSpace($BaselineLog)) {
    $BaselineLog = Resolve-LatestEvalLog -RepoRoot $Repo -ExcludePath $CandidateLog
  }
  if ([string]::IsNullOrWhiteSpace($CandidateLog) -or -not (Test-Path $CandidateLog)) {
    throw "Candidate log not found."
  }
  if ([string]::IsNullOrWhiteSpace($BaselineLog) -or -not (Test-Path $BaselineLog)) {
    throw "Baseline log not found."
  }

  Write-Host ("baseline : {0}" -f $BaselineLog)
  Write-Host ("candidate: {0}" -f $CandidateLog)

  if ($PrintOnly) { return }

  $absOutDir = if ([System.IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $Repo $OutDir }
  New-Item -ItemType Directory -Path $absOutDir -Force | Out-Null
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $outPath = Join-Path $absOutDir ("curriculum_compare_" + $stamp + ".txt")

  $commonFlag = if ($CommonOnly) { " --common-only" } else { "" }
  $cmd = ".\.venv\Scripts\python.exe .\scripts\compare_curriculum_eval_logs.py --baseline `"$BaselineLog`" --candidate `"$CandidateLog`"$commonFlag"
  Invoke-Expression $cmd | Tee-Object -FilePath $outPath
  if ($LASTEXITCODE -ne 0) {
    throw "compare_curriculum_eval_logs.py failed with exit code $LASTEXITCODE"
  }
  Write-Host ("Saved compare report: {0}" -f $outPath)
}
finally {
  Pop-Location
}
