param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  $statusPath = Join-Path $Repo "runs_curriculum\experiments\reporting\catalog_publish_status.json"
  if (Test-Path $statusPath) {
    Write-Host "Current publication status:" -ForegroundColor Yellow
    Get-Content $statusPath -Raw | Write-Host
  } else {
    Write-Host "No previous status file found; running repair publish anyway." -ForegroundColor Yellow
  }

  Write-Host "Running publication repair..."
  python -c "from pathlib import Path; import json; from mlops.catalog_publisher_v2 import publish_catalog_snapshot; print(json.dumps(publish_catalog_snapshot(repo_root=Path('.').resolve()), indent=2))"
  if ($LASTEXITCODE -ne 0) {
    throw "Repair publication failed with exit code $LASTEXITCODE"
  }
  Write-Host "Repair publication completed."
}
finally {
  Pop-Location
}
