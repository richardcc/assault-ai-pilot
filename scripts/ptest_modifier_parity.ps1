param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Write-Host "== ptest modifier parity (ranged/close/critical) =="
  python -m pytest -q assault_model/tests/test_modifier_parity_ranged_close.py
}
finally {
  Pop-Location
}
