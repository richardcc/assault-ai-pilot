from __future__ import annotations

from pathlib import Path
from typing import Any

from mlops.contracts_v2 import SCHEMA_VERSION_V2


def build_catalog_duckdb_from_parquet(
    *,
    repo_root: Path,
    parquet_rel_dir: str = "runs_curriculum/experiments/reporting/indexes",
    duckdb_rel_path: str = "runs_curriculum/experiments/reporting/reporting.duckdb",
) -> dict[str, Any]:
    parquet_dir = (repo_root / str(parquet_rel_dir)).resolve()
    models_pq = parquet_dir / "catalog_models.parquet"
    evals_pq = parquet_dir / "catalog_evals.parquet"
    trains_pq = parquet_dir / "catalog_trains.parquet"
    eval_result_sides_pq = parquet_dir / "catalog_eval_result_sides.parquet"
    out_db = (repo_root / str(duckdb_rel_path)).resolve()
    out_db.parent.mkdir(parents=True, exist_ok=True)
    if not models_pq.exists() or not evals_pq.exists() or not trains_pq.exists():
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION_V2,
            "error": f"parquet indexes missing under {parquet_dir}",
            "duckdb_path": str(out_db),
        }
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION_V2,
            "error": f"duckdb import failed: {exc}",
            "duckdb_path": str(out_db),
        }
    con = duckdb.connect(str(out_db))
    try:
        try:
            con.execute(f"CREATE OR REPLACE TABLE catalog_models AS SELECT * FROM read_parquet('{models_pq.as_posix()}')")
        except Exception:
            con.execute(
                """
                CREATE OR REPLACE TABLE catalog_models AS
                SELECT
                    ''::VARCHAR AS schema_version,
                    ''::VARCHAR AS engine,
                    ''::VARCHAR AS model_id,
                    ''::VARCHAR AS config_fingerprint,
                    0::BIGINT AS train_runs,
                    0::BIGINT AS eval_runs,
                    ''::VARCHAR AS latest_train_run_id,
                    ''::VARCHAR AS latest_train_created_at_utc,
                    ''::VARCHAR AS latest_eval_created_at_utc
                WHERE FALSE
                """
            )
        try:
            con.execute(f"CREATE OR REPLACE TABLE catalog_evals AS SELECT * FROM read_parquet('{evals_pq.as_posix()}')")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS results_count BIGINT")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS has_results BOOLEAN")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS head_diagnostics_json VARCHAR")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS diagnostics_summary_json VARCHAR")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS phase_gate_json VARCHAR")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS scenario_ids_json VARCHAR")
            con.execute("ALTER TABLE catalog_evals ADD COLUMN IF NOT EXISTS compact_results_json VARCHAR")
        except Exception:
            con.execute(
                """
                CREATE OR REPLACE TABLE catalog_evals AS
                SELECT
                    ''::VARCHAR AS schema_version,
                    ''::VARCHAR AS engine,
                    ''::VARCHAR AS model_id,
                    ''::VARCHAR AS eval_id,
                    ''::VARCHAR AS train_run_id,
                    ''::VARCHAR AS scenario_id,
                    ''::VARCHAR AS created_at_utc,
                    ''::VARCHAR AS source_path,
                    ''::VARCHAR AS curriculum_phase,
                    0::BIGINT AS results_count,
                    FALSE::BOOLEAN AS has_results,
                    NULL::VARCHAR AS head_diagnostics_json,
                    NULL::VARCHAR AS diagnostics_summary_json,
                    NULL::VARCHAR AS phase_gate_json,
                    NULL::VARCHAR AS scenario_ids_json,
                    NULL::VARCHAR AS compact_results_json
                WHERE FALSE
                """
            )
        try:
            con.execute(f"CREATE OR REPLACE TABLE catalog_trains AS SELECT * FROM read_parquet('{trains_pq.as_posix()}')")
            con.execute("ALTER TABLE catalog_trains ADD COLUMN IF NOT EXISTS summary_json VARCHAR")
            con.execute("ALTER TABLE catalog_trains ADD COLUMN IF NOT EXISTS observation_channels_json VARCHAR")
            con.execute("ALTER TABLE catalog_trains ADD COLUMN IF NOT EXISTS channel_effectiveness_json VARCHAR")
        except Exception:
            con.execute(
                """
                CREATE OR REPLACE TABLE catalog_trains AS
                SELECT
                    ''::VARCHAR AS schema_version,
                    ''::VARCHAR AS engine,
                    ''::VARCHAR AS model_id,
                    ''::VARCHAR AS run_id,
                    ''::VARCHAR AS scenario_id,
                    ''::VARCHAR AS created_at_utc,
                    ''::VARCHAR AS git_commit,
                    FALSE::BOOLEAN AS is_retrain,
                    ''::VARCHAR AS parent_run_id,
                    ''::VARCHAR AS curriculum_phase,
                    ''::VARCHAR AS latest_checkpoint,
                    NULL::VARCHAR AS summary_json,
                    NULL::VARCHAR AS observation_channels_json,
                    NULL::VARCHAR AS channel_effectiveness_json
                WHERE FALSE
                """
            )
        try:
            con.execute(
                f"CREATE OR REPLACE TABLE catalog_eval_result_sides AS "
                f"SELECT * FROM read_parquet('{eval_result_sides_pq.as_posix()}')"
            )
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS seed BIGINT")
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS opponent_controller VARCHAR")
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS curriculum_phase VARCHAR")
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS units_alive_final DOUBLE")
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS units_lost DOUBLE")
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS enemy_units_eliminated DOUBLE")
            con.execute("ALTER TABLE catalog_eval_result_sides ADD COLUMN IF NOT EXISTS damage_dealt DOUBLE")
        except Exception:
            con.execute(
                """
                CREATE OR REPLACE TABLE catalog_eval_result_sides AS
                SELECT
                    ''::VARCHAR AS schema_version,
                    ''::VARCHAR AS engine,
                    ''::VARCHAR AS model_id,
                    ''::VARCHAR AS eval_id,
                    ''::VARCHAR AS train_run_id,
                    ''::VARCHAR AS scenario_id,
                    ''::VARCHAR AS created_at_utc,
                    ''::VARCHAR AS source_path,
                    ''::VARCHAR AS curriculum_phase,
                    ''::VARCHAR AS matchup_profile,
                    ''::VARCHAR AS agent_name,
                    ''::VARCHAR AS side,
                    ''::VARCHAR AS controller,
                    ''::VARCHAR AS opponent_controller,
                    NULL::BIGINT AS seed,
                    0::BIGINT AS episodes,
                    0.0::DOUBLE AS win_rate,
                    0.0::DOUBLE AS draw_rate,
                    0.0::DOUBLE AS loss_rate,
                    0.0::DOUBLE AS total_victory_rate,
                    0.0::DOUBLE AS victory_rate,
                    0.0::DOUBLE AS defeat_rate,
                    0.0::DOUBLE AS total_defeat_rate,
                    0.0::DOUBLE AS avg_return,
                    0.0::DOUBLE AS tracked_captured_avg,
                    NULL::DOUBLE AS vp_net_avg_side,
                    NULL::DOUBLE AS winner_rate_side,
                    NULL::DOUBLE AS units_alive_final,
                    NULL::DOUBLE AS units_lost,
                    NULL::DOUBLE AS enemy_units_eliminated,
                    NULL::DOUBLE AS damage_dealt
                WHERE FALSE
                """
            )
        con.execute(
            "CREATE OR REPLACE TABLE catalog_meta AS "
            "SELECT ? AS schema_version, now()::VARCHAR AS generated_at_utc, ? AS parquet_dir",
            [SCHEMA_VERSION_V2, str(parquet_dir)],
        )
        return {
            "ok": True,
            "schema_version": SCHEMA_VERSION_V2,
            "duckdb_path": str(out_db),
            "models_rows": int(con.execute("SELECT COUNT(*) FROM catalog_models").fetchone()[0]),
            "evals_rows": int(con.execute("SELECT COUNT(*) FROM catalog_evals").fetchone()[0]),
            "trains_rows": int(con.execute("SELECT COUNT(*) FROM catalog_trains").fetchone()[0]),
            "eval_result_sides_rows": int(con.execute("SELECT COUNT(*) FROM catalog_eval_result_sides").fetchone()[0]),
        }
    finally:
        con.close()


def load_catalog_summary_from_duckdb(
    *,
    repo_root: Path,
    duckdb_rel_path: str = "runs_curriculum/experiments/reporting/reporting.duckdb",
) -> dict[str, Any]:
    db_path = (repo_root / str(duckdb_rel_path)).resolve()
    if not db_path.exists():
        return {"error": f"duckdb catalog not found: {db_path}"}
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return {"error": f"duckdb import failed: {exc}", "engines": []}

    import time
    con = None
    last_exc = None
    for attempt in range(6):
        try:
            con = duckdb.connect(str(db_path), read_only=True)
            break
        except Exception as exc:
            last_exc = exc
            if attempt < 5:
                time.sleep(0.15 * (attempt + 1))
    if con is None:
        return {"error": f"duckdb database temporarily busy/locked: {last_exc}", "engines": []}

    try:
        model_rows = con.execute(
            """
            SELECT
                engine,
                model_id,
                config_fingerprint,
                COALESCE(train_runs, 0) AS train_runs,
                COALESCE(eval_runs, 0) AS eval_runs,
                COALESCE(latest_train_run_id, '') AS latest_train_run_id,
                COALESCE(latest_train_created_at_utc, '') AS latest_train_created_at_utc,
                COALESCE(latest_eval_created_at_utc, '') AS latest_eval_created_at_utc
            FROM catalog_models
            ORDER BY engine, model_id
            """
        ).fetchall()
        train_counts_rows = con.execute(
            """
            SELECT engine, model_id, COUNT(*) AS train_runs_real
            FROM catalog_trains
            GROUP BY engine, model_id
            """
        ).fetchall()
        latest_train_rows = con.execute(
            """
            SELECT engine, model_id, MAX(created_at_utc) AS latest_train_created_at_utc
            FROM catalog_trains
            GROUP BY engine, model_id
            """
        ).fetchall()
        eval_counts_rows = con.execute(
            """
            SELECT engine, model_id, COUNT(*) AS eval_runs_real
            FROM catalog_evals
            GROUP BY engine, model_id
            """
        ).fetchall()
        latest_eval_rows = con.execute(
            """
            SELECT engine, model_id, MAX(created_at_utc) AS latest_eval_created_at_utc
            FROM catalog_evals
            GROUP BY engine, model_id
            """
        ).fetchall()
    except Exception as exc:
        return {"error": f"duckdb query failed: {exc}"}
    finally:
        con.close()

    train_counts_by_key: dict[tuple[str, str], int] = {}
    for row in list(train_counts_rows or []):
        key = (str(row[0] or ""), str(row[1] or ""))
        train_counts_by_key[key] = int(row[2] or 0)
    eval_counts_by_key: dict[tuple[str, str], int] = {}
    for row in list(eval_counts_rows or []):
        key = (str(row[0] or ""), str(row[1] or ""))
        eval_counts_by_key[key] = int(row[2] or 0)
    latest_train_by_key: dict[tuple[str, str], str] = {}
    for row in list(latest_train_rows or []):
        key = (str(row[0] or ""), str(row[1] or ""))
        latest_train_by_key[key] = str(row[2] or "")
    latest_eval_by_key: dict[tuple[str, str], str] = {}
    for row in list(latest_eval_rows or []):
        key = (str(row[0] or ""), str(row[1] or ""))
        latest_eval_by_key[key] = str(row[2] or "")

    by_engine: dict[str, list[dict[str, Any]]] = {}
    for row in model_rows:
        engine = str(row[0] or "")
        model_id = str(row[1] or "")
        key = (engine, model_id)
        train_runs_real = int(train_counts_by_key.get(key, int(row[3] or 0)))
        eval_runs_real = int(eval_counts_by_key.get(key, int(row[4] or 0)))
        models = by_engine.setdefault(engine, [])
        models.append(
            {
                "model_id": model_id,
                "engine": engine,
                "algorithm": engine,
                "config_fingerprint": str(row[2] or ""),
                "train_runs_count": int(train_runs_real),
                # DuckDB summary endpoint is count-first (no eval rows embedded).
                # Expose a stable badge in model list: eval=<total>, not 0/<total>.
                "eval_history_total_count": int(eval_runs_real),
                "eval_history_visible_count": int(eval_runs_real),
                "eval_history_truncated": False,
                "latest_train_run_id": str(row[5] or ""),
                "latest_train_created_at_utc": str(
                    latest_train_by_key.get(key, str(row[6] or ""))
                ),
                "latest_eval_created_at_utc": str(
                    latest_eval_by_key.get(key, str(row[7] or ""))
                ),
                "train_history": [],
                "eval_history": [],
                "scenarios_seen": [],
                "scenario_train_counts": {},
                "scenario_eval_counts": {},
            }
        )

    engines = []
    for engine_name in ["efficientzero_v2", "sb3", "muzero", "alpha"]:
        eng_models = list(by_engine.get(engine_name, []))
        eng_models.sort(
            key=lambda m: (
                max(
                    str(m.get("latest_train_created_at_utc") or ""),
                    str(m.get("latest_eval_created_at_utc") or ""),
                ),
                str(m.get("model_id") or ""),
            ),
            reverse=True,
        )
        engines.append(
            {
                "engine": engine_name,
                "models": eng_models,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION_V2,
        "catalog_mode": "duckdb_primary",
        "catalog_source": "duckdb",
        "repo_root": str(repo_root),
        "engines": engines,
    }

