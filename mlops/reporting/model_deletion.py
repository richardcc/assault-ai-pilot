from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any

from mlops.catalog_publisher_v2 import publish_catalog_snapshot


def _remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def delete_model_experiment(
    repo_root: Path,
    model_id: str,
    *,
    engine: str = "",
) -> dict[str, Any]:
    model_id = str(model_id or "").strip()
    if not model_id or not re.match(r"^[a-zA-Z0-9_\-]+$", model_id):
        raise ValueError(f"Invalid model_id: {model_id}")

    reporting_dir = (repo_root / "runs_curriculum" / "experiments" / "reporting").resolve()
    duckdb_path = reporting_dir / "reporting.duckdb"

    # Identify runs associated with this model
    run_ids: set[str] = set()

    # 1. From DuckDB if present
    if duckdb_path.exists():
        try:
            import duckdb
            ro_con = duckdb.connect(str(duckdb_path), read_only=True)
            try:
                rows = ro_con.execute("SELECT DISTINCT run_id FROM catalog_trains WHERE model_id = ?", [model_id]).fetchall()
                for r in rows:
                    if r[0]:
                        run_ids.add(str(r[0]))
                rows = ro_con.execute("SELECT DISTINCT eval_id FROM catalog_evals WHERE model_id = ?", [model_id]).fetchall()
                for r in rows:
                    if r[0]:
                        run_ids.add(str(r[0]))
                rows = ro_con.execute("SELECT DISTINCT train_run_id FROM catalog_evals WHERE model_id = ?", [model_id]).fetchall()
                for r in rows:
                    if r[0]:
                        run_ids.add(str(r[0]))
            finally:
                ro_con.close()
        except Exception:
            pass

    # 2. From model_id name directly
    # e.g. efficientzero_v2_efficientzero_v2_f99c82b1 -> efficientzero_v2_f99c82b1
    # or muzero_muzero_251d9f95 -> muzero_251d9f95
    for candidate_prefix in ["efficientzero_v2_", "muzero_"]:
        if model_id.startswith(f"{candidate_prefix}{candidate_prefix}"):
            sub = model_id[len(candidate_prefix):]
            run_ids.add(sub)
    run_ids.add(model_id)

    # 3. Check existing directories in runs/ or runs_curriculum/ matching or having manifest pointing to model_id
    for base_dir in ["runs", "runs_curriculum"]:
        base_p = repo_root / base_dir
        if not base_p.exists():
            continue
        for rd in base_p.iterdir():
            if not rd.is_dir():
                continue
            if rd.name in run_ids or rd.name == model_id:
                run_ids.add(rd.name)
            else:
                m_path = rd / "run_manifest.json"
                if m_path.exists():
                    try:
                        m_data = json.loads(m_path.read_text(encoding="utf-8"))
                        if m_data.get("model_id") == model_id:
                            run_ids.add(rd.name)
                    except Exception:
                        pass

    # 4. Delete matching directories on disk
    freed_bytes = 0
    deleted_dirs: list[str] = []
    for rid in run_ids:
        for base_dir in ["runs", "runs_curriculum"]:
            d = (repo_root / base_dir / rid).resolve()
            if d.exists() and d.is_dir():
                try:
                    for root, _, files in os.walk(d):
                        for f in files:
                            try:
                                freed_bytes += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass
                except Exception:
                    pass
                shutil.rmtree(d, onerror=_remove_readonly)
                deleted_dirs.append(str(d))

    # 5. Clean traceability
    trace_path = reporting_dir / "curriculum_phase_traceability.jsonl"
    if trace_path.exists():
        try:
            lines = trace_path.read_text(encoding="utf-8").splitlines()
            kept_lines = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if str(obj.get("train_run_id", "") or "") not in run_ids:
                        kept_lines.append(line)
                except Exception:
                    kept_lines.append(line)
            trace_path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
        except Exception:
            pass

    trace_latest = reporting_dir / "curriculum_phase_traceability.latest.json"
    if trace_latest.exists():
        try:
            obj = json.loads(trace_latest.read_text(encoding="utf-8"))
            if str(obj.get("train_run_id", "") or "") in run_ids:
                trace_latest.unlink(missing_ok=True)
        except Exception:
            pass

    # 6. Delete directly from DuckDB and update Parquet indexes & slim catalog in-place
    pub_res = {"catalog_mode": "duckdb_in_place_fast"}
    try:
        import duckdb  # type: ignore
        from mlops.reporting.catalog_duckdb import (
            close_duckdb_readonly_connection,
            load_catalog_summary_from_duckdb,
            _DUCKDB_READONLY_LOCK,
            _CATALOG_SUMMARY_CACHE,
        )
        from mlops.catalog_publisher_v2 import _atomic_write_json
        from mlops.contracts_v2 import SCHEMA_VERSION_V2

        indexes_dir = reporting_dir / "indexes"
        if duckdb_path.exists():
            with _DUCKDB_READONLY_LOCK:
                # Close cached read-only connection in this process to prevent lock conflicts
                close_duckdb_readonly_connection(duckdb_path)
                _CATALOG_SUMMARY_CACHE.pop(str(duckdb_path.resolve()), None)

                con = None
                for attempt in range(6):
                    try:
                        con = duckdb.connect(str(duckdb_path))
                        break
                    except Exception as conn_err:
                        if attempt < 5:
                            import time
                            time.sleep(0.06 * (attempt + 1))
                        else:
                            raise conn_err

                try:
                    for rid in run_ids:
                        con.execute("DELETE FROM catalog_trains WHERE run_id = ?", [rid])
                        con.execute("DELETE FROM catalog_evals WHERE train_run_id = ?", [rid])
                        con.execute("DELETE FROM catalog_evals WHERE eval_id = ?", [rid])
                        con.execute("DELETE FROM catalog_eval_result_sides WHERE train_run_id = ?", [rid])
                        con.execute("DELETE FROM catalog_eval_result_sides WHERE eval_id = ?", [rid])
                    con.execute("DELETE FROM catalog_models WHERE model_id = ?", [model_id])
                    con.execute("DELETE FROM catalog_trains WHERE model_id = ?", [model_id])
                    con.execute("DELETE FROM catalog_evals WHERE model_id = ?", [model_id])
                    con.execute("DELETE FROM catalog_eval_result_sides WHERE model_id = ?", [model_id])

                    if indexes_dir.exists():
                        con.execute(f"COPY catalog_models TO '{(indexes_dir / 'catalog_models.parquet').as_posix()}' (FORMAT PARQUET)")
                        con.execute(f"COPY catalog_trains TO '{(indexes_dir / 'catalog_trains.parquet').as_posix()}' (FORMAT PARQUET)")
                        con.execute(f"COPY catalog_evals TO '{(indexes_dir / 'catalog_evals.parquet').as_posix()}' (FORMAT PARQUET)")
                        con.execute(f"COPY catalog_eval_result_sides TO '{(indexes_dir / 'catalog_eval_result_sides.parquet').as_posix()}' (FORMAT PARQUET)")
                finally:
                    if con is not None:
                        con.close()
                    # Ensure read-only pool and summary caches are invalidated for subsequent requests
                    close_duckdb_readonly_connection(duckdb_path)
                    _CATALOG_SUMMARY_CACHE.pop(str(duckdb_path.resolve()), None)

            slim_payload = load_catalog_summary_from_duckdb(repo_root=repo_root)
            if slim_payload:
                slim_payload["schema_version"] = SCHEMA_VERSION_V2
                slim_payload["catalog_mode"] = "duckdb_primary_fast_delete"
                pub_res["catalog_mode"] = "duckdb_primary_fast_delete"
                out_catalog = reporting_dir / "model_catalog_latest.json"
                _atomic_write_json(out_catalog, slim_payload)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("In-place fast deletion failed (%s); falling back to publish_catalog_snapshot", exc)
        pub_res = publish_catalog_snapshot(repo_root=repo_root, include_debug_full_catalog=False)

    return {
        "ok": True,
        "model_id": model_id,
        "deleted_run_ids": sorted(list(run_ids)),
        "deleted_directories": deleted_dirs,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "catalog_mode": pub_res.get("catalog_mode", "ok"),
    }
