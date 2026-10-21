"""
mlops/tests/test_unified_catalog_and_schema_purge.py

Automated Test Suite for Roadmap Task 1.4 (Priority P1):
Catálogo Unificado y Depuración de Esquemas.

Verifications:
1. Canonical Decisions Schema Invariants (exactly 15 columns, zero accumulator leakage).
2. Zero-Leakage in build_eval_decision_summary output.
3. Clean Break with MuZero: Controller labels in DuckDB / Parquet are strictly 'EfficientZeroV2'.
4. Automatic Parquet Purge & Migration Engine (purge_single_decisions_top_parquet).
5. DuckDB Rebuild & Schema Conformance Verification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from assault_bench.decision_metrics import build_eval_decision_summary
from mlops.dataset_builder import (
    CANONICAL_DECISIONS_TOP_COLUMNS,
    OBSOLETE_DECISION_ACCUMULATOR_COLUMNS,
    purge_legacy_controllers_in_catalog,
    purge_single_decisions_top_parquet,
    rebuild_unified_duckdb,
    run_full_schema_purge_and_unification,
)


def test_canonical_decisions_top_schema_definition() -> None:
    """Verify that canonical schema defines exactly 15 non-leaky columns."""
    assert len(CANONICAL_DECISIONS_TOP_COLUMNS) == 15
    for obsolete_col in OBSOLETE_DECISION_ACCUMULATOR_COLUMNS:
        assert obsolete_col not in CANONICAL_DECISIONS_TOP_COLUMNS


def test_decision_metrics_enrich_does_not_leak_accumulators() -> None:
    """Verify that build_eval_decision_summary does not leak accumulator columns into top_actions."""
    synthetic_trace_rows = [
        {
            "action_id": "MOVE:US_1:5:5",
            "action_kind": "MOVE",
            "unit_side": "US",
            "target_q": 5,
            "target_r": 5,
            "attack_distance": 2.0,
            "attack_target_cover": 0.4,
            "attack_target_los_block": 0.0,
            "damage_dealt": 1.0,
            "kills_dealt": 0.0,
        },
        {
            "action_id": "ASSAULT:US_1:5:5",
            "action_kind": "ASSAULT",
            "unit_side": "US",
            "target_q": 5,
            "target_r": 5,
            "attack_distance": 0.0,
            "attack_target_cover": 0.1,
            "attack_target_los_block": 0.0,
            "damage_dealt": 2.0,
            "kills_dealt": 1.0,
        },
    ]

    summary, top_actions = build_eval_decision_summary(synthetic_trace_rows)
    assert len(top_actions) > 0

    for action_entry in top_actions:
        keys = set(action_entry.keys())
        # Assert zero accumulator leakage
        assert not keys.intersection(OBSOLETE_DECISION_ACCUMULATOR_COLUMNS), (
            f"Leaked accumulator keys found: {keys.intersection(OBSOLETE_DECISION_ACCUMULATOR_COLUMNS)}"
        )
        # Assert canonical keys exist
        assert "damage_per_action" in keys
        assert "kills_per_action" in keys
        assert "target_q_avg" in keys
        assert "attack_distance_avg" in keys


def test_purge_single_decisions_top_parquet_migrates_legacy(tmp_path: Path) -> None:
    """Test that purge_single_decisions_top_parquet drops accumulator cols and standardizes to 15 cols."""
    legacy_parquet = tmp_path / "decisions_top.parquet"

    # Create a 23-column legacy parquet
    legacy_data: Dict[str, list] = {
        "action_id": ["MOVE:GE_1:3:4"],
        "action_kind": ["MOVE"],
        "unit_side": ["GE"],
        "count": [5.0],
        "damage_sum": [10.0],
        "kills_sum": [2.0],
        "damage_per_action": [2.0],
        "kills_per_action": [0.4],
        "target_q_avg": [3.0],
        "target_r_avg": [4.0],
        "attack_distance_avg": [1.0],
        "attack_target_cover_avg": [0.3],
        "attack_target_los_block_avg": [0.0],
        "latent_top_dims": ["dim_12"],
        "latent_top_dims_mode_count": [4.0],
        # 8 legacy accumulator columns:
        "target_q_sum": [15.0],
        "target_q_n": [5.0],
        "target_r_sum": [20.0],
        "target_r_n": [5.0],
        "cover_sum": [1.5],
        "cover_n": [5.0],
        "los_sum": [0.0],
        "los_n": [5.0],
    }

    pq.write_table(pa.Table.from_pydict(legacy_data), legacy_parquet)

    # Initial check: 23 columns
    assert len(pq.read_schema(legacy_parquet).names) == 23

    # Purge
    result = purge_single_decisions_top_parquet(legacy_parquet)
    assert result["status"] == "purged"
    assert result["columns_before"] == 23
    assert result["columns_after"] == 15
    assert len(result["dropped_columns"]) == 8

    # Verify purged schema
    purged_schema = pq.read_schema(legacy_parquet)
    assert purged_schema.names == CANONICAL_DECISIONS_TOP_COLUMNS

    # Running again should report already_canonical
    result_second = purge_single_decisions_top_parquet(legacy_parquet)
    assert result_second["status"] == "already_canonical"


def test_repository_active_decisions_parquet_are_canonical() -> None:
    """Verify that 100% of active decisions_top.parquet files in repo conform to canonical schema."""
    repo_root = Path(__file__).resolve().parents[2]
    search_dirs = [repo_root / "runs_curriculum", repo_root / "runs"]

    files_checked = 0
    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for p_file in s_dir.glob("**/indexed/decisions_top.parquet"):
            schema = pq.read_schema(p_file)
            assert schema.names == CANONICAL_DECISIONS_TOP_COLUMNS, (
                f"File {p_file} has non-canonical columns: {schema.names}"
            )
            files_checked += 1

    assert files_checked > 0, "No decisions_top.parquet files found to verify"


def test_duckdb_and_catalog_zero_muzero_controllers() -> None:
    """Verify that catalog Parquet and DuckDB contain zero 'MuZero' controller labels."""
    repo_root = Path(__file__).resolve().parents[2]
    db_report = rebuild_unified_duckdb(repo_root)

    assert db_report["ok"] is True
    assert db_report["muzero_legacy_count"] == 0
    assert db_report["verified_zero_legacy"] is True
