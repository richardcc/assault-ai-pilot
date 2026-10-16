param(
  [string]$Repo = "C:\repos\python\assault",
  [ValidateSet("cpu", "cuda", "auto")]
  [string]$Device = "cpu",
  [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Action
  )
  Write-Host ""
  Write-Host "== $Name ==" -ForegroundColor Cyan
  & $Action
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  if (-not $SkipSmoke) {
    Invoke-Step "Smoke Train+Eval+Catalog" {
      powershell -ExecutionPolicy Bypass -File ".\scripts\run_smoke_train_eval_v2_catalog.ps1" -Repo $Repo -Device $Device
      if ($LASTEXITCODE -ne 0) {
        throw "Smoke script failed with exit code $LASTEXITCODE"
      }
    }
  } else {
    Write-Host "Skipping smoke step (--SkipSmoke)." -ForegroundColor Yellow
  }

  Invoke-Step "Contract + Storage v2 tests" {
    python -m pytest mlops/tests/test_contracts_v2.py mlops/tests/test_storage_v2.py -q
    if ($LASTEXITCODE -ne 0) {
      throw "Contracts/Storage tests failed with exit code $LASTEXITCODE"
    }
  }

  Invoke-Step "Catalog publisher + strict loading tests" {
    python -m pytest mlops/tests/test_catalog_publisher_v2.py mlops/tests/test_reporting_viewer_catalog_loading.py -q
    if ($LASTEXITCODE -ne 0) {
      throw "Catalog publisher/loading tests failed with exit code $LASTEXITCODE"
    }
  }

  Invoke-Step "Catalog + API v2 tests" {
    python -m pytest mlops/tests/test_reporting_catalog.py mlops/tests/test_reporting_viewer_api_v2.py -q
    if ($LASTEXITCODE -ne 0) {
      throw "Catalog/API v2 tests failed with exit code $LASTEXITCODE"
    }
  }

  Invoke-Step "Viewer replay filter tests" {
    python -m pytest mlops/tests/test_reporting_viewer_replay_filter.py -q
    if ($LASTEXITCODE -ne 0) {
      throw "Viewer replay filter tests failed with exit code $LASTEXITCODE"
    }
  }

  Invoke-Step "Reporting persistence perf gate" {
    powershell -ExecutionPolicy Bypass -File ".\scripts\gate_reporting_persistence_perf.ps1" -Repo $Repo
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Perf gate failed. Attempting one-shot publication repair..." -ForegroundColor Yellow
      powershell -ExecutionPolicy Bypass -File ".\scripts\repair_catalog_publication_v2.ps1" -Repo $Repo
      if ($LASTEXITCODE -ne 0) {
        throw "Persistence perf gate failed and repair script failed."
      }
      powershell -ExecutionPolicy Bypass -File ".\scripts\gate_reporting_persistence_perf.ps1" -Repo $Repo
      if ($LASTEXITCODE -ne 0) {
        throw "Persistence perf gate failed after repair with exit code $LASTEXITCODE"
      }
    }
  }

  Write-Host ""
  Write-Host "============================================" -ForegroundColor Green
  Write-Host "GO: reporting v2 strict gate PASSED" -ForegroundColor Green
  Write-Host "============================================" -ForegroundColor Green
}
catch {
  Write-Host ""
  Write-Host "============================================" -ForegroundColor Red
  Write-Host "NO-GO: reporting v2 strict gate FAILED" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host "============================================" -ForegroundColor Red
  exit 2
}
finally {
  Pop-Location
}
