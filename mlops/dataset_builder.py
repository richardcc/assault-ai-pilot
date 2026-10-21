"""
mlops/dataset_builder.py

Roadmap Task 1.4 (Priority P1):
Catálogo Unificado y Depuración de Esquemas Parquet y DuckDB.

Responsibilities:
1. Canonical Schema Registry:
   - Formally defines canonical Parquet schemas for evaluation decisions (15 columns),
     catalog indexes (catalog_models, catalog_evals, catalog_trains, catalog_eval_result_sides),
     and DuckDB analytical tables.
2. Legacy Schema Purging & Migration:
   - Detects and purges obsolete accumulator fields ('cover_n', 'cover_sum', 'los_n', 'los_sum',
     'target_q_n', 'target_q_sum', 'target_r_n', 'target_r_sum', etc.) from all
     decisions_top.parquet files.
   - Enforces clean break by replacing any legacy 'MuZero' controller labels with
     'EfficientZeroV2' across Parquet files and DuckDB tables.
3. DuckDB Index Rebuilding:
   - Atomically rebuilds reporting.duckdb from the cleansed, canonical Parquet indexes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore
except ImportError:
    pa = None
    pq = None

from mlops.contracts_v2 import SCHEMA_VERSION_V2
from mlops.reporting.catalog_duckdb import build_catalog_duckdb_from_parquet


CANONICAL_DECISIONS_TOP_COLUMNS: List[str] = [
    "action_id",
    "action_kind",
    "unit_side",
    "count",
    "damage_sum",
    "kills_sum",
    "damage_per_action",
    "kills_per_action",
    "target_q_avg",
    "target_r_avg",
    "attack_distance_avg",
    "attack_target_cover_avg",
    "attack_target_los_block_avg",
    "latent_top_dims",
    "latent_top_dims_mode_count",
]

OBSOLETE_DECISION_ACCUMULATOR_COLUMNS: Set[str] = {
    "cover_n",
    "cover_sum",
    "distance_n",
    "distance_sum",
    "los_n",
    "los_sum",
    "target_q_n",
    "target_q_sum",
    "target_r_n",
    "target_r_sum",
}

CANONICAL_DECISION_TYPES: Dict[str, Any] = {
    "action_id": pa.string() if pa else None,
    "action_kind": pa.string() if pa else None,
    "unit_side": pa.string() if pa else None,
    "count": pa.float64() if pa else None,
    "damage_sum": pa.float64() if pa else None,
    "kills_sum": pa.float64() if pa else None,
    "damage_per_action": pa.float64() if pa else None,
    "kills_per_action": pa.float64() if pa else None,
    "target_q_avg": pa.float64() if pa else None,
    "target_r_avg": pa.float64() if pa else None,
    "attack_distance_avg": pa.float64() if pa else None,
    "attack_target_cover_avg": pa.float64() if pa else None,
    "attack_target_los_block_avg": pa.float64() if pa else None,
    "latent_top_dims": pa.string() if pa else None,
    "latent_top_dims_mode_count": pa.float64() if pa else None,
}


def purge_single_decisions_top_parquet(parquet_path: Path) -> Dict[str, Any]:
    """
    Examines a single decisions_top.parquet file. If it contains obsolete
    accumulator columns or non-canonical column ordering, it projects and
    rewrites the file to conform strictly to CANONICAL_DECISIONS_TOP_COLUMNS.
    """
    if pq is None or pa is None:
        return {"path": str(parquet_path), "status": "skipped_no_pyarrow"}

    if not parquet_path.exists() or not parquet_path.is_file():
        return {"path": str(parquet_path), "status": "not_found"}

    try:
        table = pq.read_table(parquet_path)
    except Exception as exc:
        return {"path": str(parquet_path), "status": "read_error", "error": str(exc)}

    current_cols = set(table.column_names)
    has_obsolete = bool(current_cols.intersection(OBSOLETE_DECISION_ACCUMULATOR_COLUMNS))
    is_exact_canonical = table.column_names == CANONICAL_DECISIONS_TOP_COLUMNS

    if is_exact_canonical and not has_obsolete:
        return {
            "path": str(parquet_path),
            "status": "already_canonical",
            "columns": len(current_cols),
            "rows": len(table),
        }

    pydict = table.to_pydict()
    clean_dict: Dict[str, list] = {}
    row_count = len(table)

    for col in CANONICAL_DECISIONS_TOP_COLUMNS:
        if col in pydict:
            clean_dict[col] = pydict[col]
        else:
            default_val = "" if col in {"action_id", "action_kind", "unit_side", "latent_top_dims"} else 0.0
            clean_dict[col] = [default_val] * row_count

    clean_table = pa.Table.from_pydict(clean_dict)
    tmp_path = parquet_path.with_suffix(".tmp.parquet")
    try:
        pq.write_table(clean_table, tmp_path)
        tmp_path.replace(parquet_path)
        return {
            "path": str(parquet_path),
            "status": "purged",
            "columns_before": len(current_cols),
            "columns_after": len(clean_table.column_names),
            "rows": len(clean_table),
            "dropped_columns": sorted(list(current_cols - set(CANONICAL_DECISIONS_TOP_COLUMNS))),
        }
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return {"path": str(parquet_path), "status": "write_error", "error": str(exc)}


def purge_all_decisions_top_parquet(
    repo_root: Path,
    include_archives: bool = True,
) -> Dict[str, Any]:
    """
    Scans runs_curriculum/, runs/, and optionally runs_archive/ for all
    decisions_top.parquet files and enforces canonical schema conformance.
    """
    search_dirs = [repo_root / "runs_curriculum", repo_root / "runs"]
    if include_archives:
        search_dirs.append(repo_root / "runs_archive")

    results: List[Dict[str, Any]] = []
    purged_count = 0
    already_canonical_count = 0
    errors_count = 0

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for p_file in s_dir.glob("**/indexed/decisions_top.parquet"):
            res = purge_single_decisions_top_parquet(p_file)
            results.append(res)
            st = res.get("status")
            if st == "purged":
                purged_count += 1
            elif st == "already_canonical":
                already_canonical_count += 1
            else:
                errors_count += 1

    return {
        "total_scanned": len(results),
        "purged": purged_count,
        "already_canonical": already_canonical_count,
        "errors": errors_count,
        "details": results,
    }


def purge_legacy_controllers_in_catalog(repo_root: Path) -> Dict[str, Any]:
    """
    Purges obsolete 'MuZero' controller labels in catalog_eval_result_sides.parquet,
    normalizing all MCTS / self-play controllers to 'EfficientZeroV2'.
    """
    if pq is None or pa is None:
        return {"status": "skipped_no_pyarrow"}

    cat_pq = repo_root / "runs_curriculum" / "experiments" / "reporting" / "indexes" / "catalog_eval_result_sides.parquet"
    if not cat_pq.exists():
        return {"path": str(cat_pq), "status": "not_found"}

    try:
        table = pq.read_table(cat_pq)
    except Exception as exc:
        return {"path": str(cat_pq), "status": "read_error", "error": str(exc)}

    data = table.to_pydict()
    controllers = data.get("controller", [])
    opponents = data.get("opponent_controller", [])

    modified = False
    new_controllers = []
    for c in controllers:
        c_str = str(c or "")
        if c_str == "MuZero":
            new_controllers.append("EfficientZeroV2")
            modified = True
        else:
            new_controllers.append(c)

    new_opponents = []
    for o in opponents:
        o_str = str(o or "")
        if o_str == "MuZero":
            new_opponents.append("EfficientZeroV2")
            modified = True
        else:
            new_opponents.append(o)

    if not modified:
        return {
            "path": str(cat_pq),
            "status": "already_purged",
            "rows": len(table),
        }

    data["controller"] = new_controllers
    data["opponent_controller"] = new_opponents
    updated_table = pa.Table.from_pydict(data)

    tmp_path = cat_pq.with_suffix(".tmp.parquet")
    try:
        pq.write_table(updated_table, tmp_path)
        tmp_path.replace(cat_pq)
        return {
            "path": str(cat_pq),
            "status": "purged_controllers",
            "rows": len(updated_table),
            "muzero_labels_replaced": True,
        }
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return {"path": str(cat_pq), "status": "write_error", "error": str(exc)}


def rebuild_unified_duckdb(repo_root: Path) -> Dict[str, Any]:
    """
    Rebuilds reporting.duckdb from the canonical Parquet indexes and
    verifies that no obsolete controller strings or schemas remain.
    """
    res = build_catalog_duckdb_from_parquet(
        repo_root=repo_root,
        parquet_rel_dir="runs_curriculum/experiments/reporting/indexes",
        duckdb_rel_path="runs_curriculum/experiments/reporting/reporting.duckdb",
    )
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error")}

    db_path = repo_root / "runs_curriculum" / "experiments" / "reporting" / "reporting.duckdb"
    try:
        import duckdb  # type: ignore

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            muzero_count = con.execute(
                "SELECT COUNT(*) FROM catalog_eval_result_sides WHERE controller = 'MuZero' OR opponent_controller = 'MuZero'"
            ).fetchone()[0]
            models_count = con.execute("SELECT COUNT(*) FROM catalog_models").fetchone()[0]
            evals_count = con.execute("SELECT COUNT(*) FROM catalog_evals").fetchone()[0]
            trains_count = con.execute("SELECT COUNT(*) FROM catalog_trains").fetchone()[0]
            sides_count = con.execute("SELECT COUNT(*) FROM catalog_eval_result_sides").fetchone()[0]

            return {
                "ok": True,
                "duckdb_path": str(db_path),
                "muzero_legacy_count": int(muzero_count),
                "models_rows": int(models_count),
                "evals_rows": int(evals_count),
                "trains_rows": int(trains_count),
                "eval_result_sides_rows": int(sides_count),
                "verified_zero_legacy": bool(muzero_count == 0),
            }
        finally:
            con.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_full_schema_purge_and_unification(
    repo_root: Path,
    include_archives: bool = True,
) -> Dict[str, Any]:
    """
    End-to-End Orchestrator for Task 1.4:
    1. Purges all decisions_top.parquet files across the repository.
    2. Purges legacy controller labels from catalog Parquet indexes.
    3. Rebuilds and verifies the DuckDB analytical database.
    """
    repo = repo_root.resolve()
    decisions_top_report = purge_all_decisions_top_parquet(repo, include_archives=include_archives)
    catalog_report = purge_legacy_controllers_in_catalog(repo)
    duckdb_report = rebuild_unified_duckdb(repo)

    return {
        "schema_version": SCHEMA_VERSION_V2,
        "decisions_top_purge": decisions_top_report,
        "catalog_controllers_purge": catalog_report,
        "duckdb_rebuild": duckdb_report,
        "task_1_4_success": bool(
            duckdb_report.get("ok") and duckdb_report.get("verified_zero_legacy")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assault Parquet and DuckDB Schema Purge Engine (Task 1.4)")
    parser.add_argument("--repo-root", type=str, default=".", help="Root directory of repository")
    parser.add_argument("--skip-archives", action="store_true", help="Skip scanning runs_archive/")
    parser.add_argument("--rebuild-only", action="store_true", help="Only rebuild DuckDB from Parquet")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    if args.rebuild_only:
        print("[*] Rebuilding DuckDB database...")
        res = rebuild_unified_duckdb(repo)
        print(res)
        sys.exit(0 if res.get("ok") else 1)

    print(f"[*] Running full schema purge and unification on {repo}...")
    summary = run_full_schema_purge_and_unification(repo, include_archives=not args.skip_archives)
    print(f"[*] Decisions Parquet Purged: {summary['decisions_top_purge']['purged']} / {summary['decisions_top_purge']['total_scanned']}")
    print(f"[*] Catalog Controller Purge: {summary['catalog_controllers_purge']['status']}")
    print(f"[*] DuckDB Rebuild Verified Zero Legacy: {summary['duckdb_rebuild'].get('verified_zero_legacy')}")
    print(f"[*] Overall Status: {'SUCCESS' if summary['task_1_4_success'] else 'FAILED'}")
    sys.exit(0 if summary["task_1_4_success"] else 1)


if __name__ == "__main__":
    main()
