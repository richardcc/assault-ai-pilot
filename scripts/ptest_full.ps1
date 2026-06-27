param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Write-Host "== ptest full (assault_sim + assault_model) =="
  python -m pytest -q assault_sim/tests assault_model/tests
}
finally {
  Pop-Location
}
