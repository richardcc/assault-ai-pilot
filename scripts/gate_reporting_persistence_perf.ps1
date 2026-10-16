param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$CatalogMaxMB = 64,
  [double]$CatalogParseMaxMs = 1200,
  [double]$DuckdbModelsMaxMs = 250,
  [double]$DuckdbEvalsMaxMs = 350,
  [double]$DuckdbTrainsMaxMs = 350
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  $duckdbPath = Join-Path $Repo "runs_curriculum\experiments\reporting\reporting.duckdb"
  if (-not (Test-Path $duckdbPath)) {
    Write-Host "DuckDB not found, attempting rebuild from parquet indexes..." -ForegroundColor Yellow
    python -c "from pathlib import Path; import json; from mlops.reporting.catalog_duckdb import build_catalog_duckdb_from_parquet; print(json.dumps(build_catalog_duckdb_from_parquet(repo_root=Path('.').resolve()), indent=2))"
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to build reporting.duckdb from parquet indexes. Ensure dependencies (duckdb, pyarrow) are installed."
    }
  }
  $catalogBytes = [int64]$CatalogMaxMB * 1024 * 1024
  Write-Host "== Reporting Persistence Perf Gate =="
  python -m mlops.reporting.perf_gate `
    --repo-root . `
    --catalog runs_curriculum/experiments/reporting/model_catalog_latest.json `
    --duckdb runs_curriculum/experiments/reporting/reporting.duckdb `
    --catalog-max-bytes $catalogBytes `
    --catalog-parse-max-ms $CatalogParseMaxMs `
    --duckdb-models-max-ms $DuckdbModelsMaxMs `
    --duckdb-evals-max-ms $DuckdbEvalsMaxMs `
    --duckdb-trains-max-ms $DuckdbTrainsMaxMs
  if ($LASTEXITCODE -ne 0) {
    throw "Reporting persistence perf gate FAILED with exit code $LASTEXITCODE"
  }
  Write-Host "Perf gate OK."
}
finally {
  Pop-Location
}
