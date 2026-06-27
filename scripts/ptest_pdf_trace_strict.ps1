param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Write-Host "== ptest pdf trace strict pass =="
  python -m pytest -q assault_model/tests/test_pdf_subsection_trace_strict_pass.py
}
finally {
  Pop-Location
}
