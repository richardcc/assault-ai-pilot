param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$Port = 8777,
  [string]$Catalog = "runs_curriculum/experiments/reporting/model_catalog_latest.json",
  [switch]$Dev,
  [switch]$OpenWindow
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  if ($OpenWindow) {
    Start-Process "http://127.0.0.1:$Port/"
  }
  if ($Dev) {
    while ($true) {
      python -m mlops.reporting.viewer --repo-root $Repo --host 127.0.0.1 --port $Port --catalog $Catalog --dev
      if ($LASTEXITCODE -ne 3) {
        break
      }
      Write-Host "[Viewer] restarting after code change..."
      Start-Sleep -Milliseconds 300
    }
  } else {
    python -m mlops.reporting.viewer --repo-root $Repo --host 127.0.0.1 --port $Port --catalog $Catalog
  }
}
finally {
  Pop-Location
}
