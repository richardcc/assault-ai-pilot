from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import pytest

from mlops.contracts_v2 import SCHEMA_VERSION_V2
from mlops.reporting.catalog_duckdb import (
    get_duckdb_readonly_connection,
    close_duckdb_readonly_connection,
)
from mlops.reporting.model_deletion import delete_model_experiment


def test_delete_model_experiment_fast_inplace(tmp_path: Path) -> None:
    # Set up test directories
    reporting_dir = tmp_path / "runs_curriculum" / "experiments" / "reporting"
    indexes_dir = reporting_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    duckdb_path = reporting_dir / "reporting.duckdb"

    # Set up mock run directory on disk
    model_id = "test_model_fast_del_abc"
    run_id = f"runs_curriculum_phase1_{model_id}"
    run_dir = tmp_path / "runs_curriculum" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps({"model_id": model_id, "run_id": run_id}), encoding="utf-8")
    (run_dir / "checkpoint.pt").write_bytes(b"dummy_weights" * 100)

    # Populate DuckDB tables
    con = duckdb.connect(str(duckdb_path))
    con.execute(
        """
        CREATE TABLE catalog_models (schema_version VARCHAR, engine VARCHAR, model_id VARCHAR, config_fingerprint VARCHAR, train_runs BIGINT, eval_runs BIGINT, latest_train_run_id VARCHAR, latest_train_created_at_utc VARCHAR, latest_eval_created_at_utc VARCHAR);
        CREATE TABLE catalog_trains (schema_version VARCHAR, engine VARCHAR, model_id VARCHAR, run_id VARCHAR, scenario_id VARCHAR, created_at_utc VARCHAR, git_commit VARCHAR, is_retrain BOOLEAN, parent_run_id VARCHAR, curriculum_phase VARCHAR, latest_checkpoint VARCHAR, summary_json VARCHAR, observation_channels_json VARCHAR, channel_effectiveness_json VARCHAR);
        CREATE TABLE catalog_evals (schema_version VARCHAR, engine VARCHAR, model_id VARCHAR, eval_id VARCHAR, train_run_id VARCHAR, scenario_id VARCHAR, created_at_utc VARCHAR, source_path VARCHAR, curriculum_phase VARCHAR, results_count BIGINT, has_results BOOLEAN, head_diagnostics_json VARCHAR, diagnostics_summary_json VARCHAR, phase_gate_json VARCHAR, scenario_ids_json VARCHAR, compact_results_json VARCHAR);
        CREATE TABLE catalog_eval_result_sides (schema_version VARCHAR, engine VARCHAR, model_id VARCHAR, eval_id VARCHAR, train_run_id VARCHAR, scenario_id VARCHAR, created_at_utc VARCHAR, source_path VARCHAR, curriculum_phase VARCHAR, matchup_profile VARCHAR, agent_name VARCHAR);
        """
    )
    con.execute(
        "INSERT INTO catalog_models VALUES (?, 'efficientzero_v2', ?, 'fingerprint', 1, 0, ?, '2026-10-22T10:00:00Z', '')",
        [SCHEMA_VERSION_V2, model_id, run_id],
    )
    con.execute(
        "INSERT INTO catalog_trains VALUES (?, 'efficientzero_v2', ?, ?, 'scen1', '2026-10-22T10:00:00Z', 'commit1', FALSE, '', 'phase1', '', '{}', '{}', '{}')",
        [SCHEMA_VERSION_V2, model_id, run_id],
    )
    # Export initial parquets
    con.execute(f"COPY catalog_models TO '{(indexes_dir / 'catalog_models.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY catalog_trains TO '{(indexes_dir / 'catalog_trains.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY catalog_evals TO '{(indexes_dir / 'catalog_evals.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY catalog_eval_result_sides TO '{(indexes_dir / 'catalog_eval_result_sides.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()

    # Simulate active viewer holding a read-only cached connection!
    ro_con = get_duckdb_readonly_connection(duckdb_path)
    assert ro_con is not None

    # Execute deletion and measure timing
    t0 = time.time()
    res = delete_model_experiment(tmp_path, model_id)
    elapsed = time.time() - t0

    # Ensure fast in-place mode succeeded in < 1 second without fallback
    assert res["ok"] is True
    assert res["catalog_mode"] == "duckdb_primary_fast_delete"
    assert res["freed_bytes"] > 0
    assert not run_dir.exists()
    assert elapsed < 1.0, f"Deletion took too long: {elapsed:.2f}s"

    # Verify model is completely gone from DuckDB
    check_con = duckdb.connect(str(duckdb_path), read_only=True)
    count = check_con.execute("SELECT COUNT(*) FROM catalog_models WHERE model_id = ?", [model_id]).fetchone()[0]
    check_con.close()
    assert count == 0

    close_duckdb_readonly_connection(duckdb_path)
