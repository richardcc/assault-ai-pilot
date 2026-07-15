param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Out = "runs_curriculum/experiments/reporting/model_catalog_latest.json",
  [string]$RunsRoot = "runs_curriculum,runs"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  python -m mlops.reporting.build_catalog --repo-root $Repo --out $Out --runs-root $RunsRoot
  if ($LASTEXITCODE -ne 0) {
    throw "build catalog failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
