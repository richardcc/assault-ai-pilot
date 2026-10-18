param(
  [switch]$Serve
)

$ErrorActionPreference = "Stop"

$Py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

if ($Serve) {
  & $Py -m mkdocs serve
} else {
  & $Py -m mkdocs build --clean
  if ($LASTEXITCODE -ne 0) {
    throw "mkdocs build failed (exit=$LASTEXITCODE)"
  }
  & $Py scripts/build_html_docs.py
  if ($LASTEXITCODE -ne 0) {
    throw "build_html_docs.py failed (exit=$LASTEXITCODE)"
  }
  Write-Host "Documentation site successfully generated with full embedded MDs at: site" -ForegroundColor Green
}
