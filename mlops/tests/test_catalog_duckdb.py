from pathlib import Path

from mlops.reporting.catalog_duckdb import build_catalog_duckdb_from_parquet, load_catalog_summary_from_duckdb


def test_catalog_duckdb_missing_parquet_reports_error(tmp_path: Path) -> None:
    out = build_catalog_duckdb_from_parquet(repo_root=tmp_path)
    assert out["ok"] is False
    assert "parquet indexes missing" in str(out.get("error", ""))


def test_catalog_duckdb_load_missing_db_reports_error(tmp_path: Path) -> None:
    out = load_catalog_summary_from_duckdb(repo_root=tmp_path)
    assert "duckdb catalog not found" in str(out.get("error", ""))

