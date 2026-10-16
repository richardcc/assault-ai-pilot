param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$Out = "runs_curriculum/experiments/reporting/model_catalog_latest.json",
  [string]$RunsRoot = "runs_curriculum,runs",
  [string]$OutParquetDir = "runs_curriculum/experiments/reporting/indexes"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  python -m mlops.reporting.build_catalog --repo-root $Repo --out $Out --runs-root $RunsRoot --out-parquet-dir $OutParquetDir
  if ($LASTEXITCODE -ne 0) {
    throw "build catalog failed with exit code $LASTEXITCODE"
  }
  python -c "from pathlib import Path; import json; from mlops.reporting.catalog_duckdb import build_catalog_duckdb_from_parquet; print(json.dumps(build_catalog_duckdb_from_parquet(repo_root=Path('.').resolve()), indent=2))"
  if ($LASTEXITCODE -ne 0) {
    throw "build duckdb from parquet failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
