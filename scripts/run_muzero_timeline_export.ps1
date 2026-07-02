[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$RunId = "",
  [int]$Iteration = -1,
  [int]$Episode = -1,
  [string]$Out = ""
)

$ErrorActionPreference = "Stop"

function Get-LatestMuZeroRunId {
  param([string]$RepoRoot)
  $runsRoot = Join-Path $RepoRoot "runs"
  if (-not (Test-Path -LiteralPath $runsRoot)) { return "" }
  $latest = Get-ChildItem -Path $runsRoot -Directory -Filter "muzero_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $latest) { return "" }
  return [string]$latest.Name
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") { . .\.venv\Scripts\Activate.ps1 }

  $resolvedRunId = [string]$RunId
  if ([string]::IsNullOrWhiteSpace($resolvedRunId)) {
    $resolvedRunId = Get-LatestMuZeroRunId -RepoRoot $Repo
  }
  if ([string]::IsNullOrWhiteSpace($resolvedRunId)) {
    throw "No MuZero run found. Pass -RunId explicitly."
  }

  $args = @(
    "-m", "agents.muzero.xai.timeline_exporter",
    "--repo", $Repo,
    "--run-id", $resolvedRunId
  )
  if ($Iteration -ge 0) { $args += @("--iteration", [string]$Iteration) }
  if ($Episode -ge 0) { $args += @("--episode", [string]$Episode) }
  if (-not [string]::IsNullOrWhiteSpace($Out)) { $args += @("--out", $Out) }

  Write-Host ("[MuZero] exporting timeline for run_id={0} iteration={1} episode={2}" -f $resolvedRunId, $Iteration, $Episode)
  & python @args
  if ($LASTEXITCODE -ne 0) {
    throw ("timeline export failed (exit={0})" -f $LASTEXITCODE)
  }
}
finally {
  Pop-Location
}
