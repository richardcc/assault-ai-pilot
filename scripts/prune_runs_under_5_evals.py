import os
import shutil
import stat
import sys
from pathlib import Path
import json

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import duckdb
from mlops.catalog_publisher_v2 import publish_catalog_snapshot


def _remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def main():
    repo_root = Path(__file__).resolve().parents[1]
    reporting_dir = repo_root / "runs_curriculum" / "experiments" / "reporting"
    duckdb_path = reporting_dir / "reporting.duckdb"

    if not duckdb_path.exists():
        print(f"Error: DuckDB not found at {duckdb_path}")
        return

    con = duckdb.connect(str(duckdb_path))
    # Identify models with less than 5 evals
    models_to_del = [
        row[0]
        for row in con.execute("SELECT model_id FROM catalog_models WHERE eval_runs < 5").fetchall()
    ]
    models_to_keep = [
        row[0]
        for row in con.execute("SELECT model_id FROM catalog_models WHERE eval_runs >= 5").fetchall()
    ]

    print(f"Models to keep ({len(models_to_keep)}):", models_to_keep)
    print(f"Models to delete ({len(models_to_del)}):", models_to_del)

    if not models_to_del:
        print("No models with < 5 evaluations found.")
        con.close()
        return

    placeholders = ",".join("?" for _ in models_to_del)
    train_runs_to_del = [
        row[0]
        for row in con.execute(
            f"SELECT DISTINCT run_id FROM catalog_trains WHERE model_id IN ({placeholders})",
            models_to_del,
        ).fetchall()
    ]
    con.close()

    del_run_ids = set(train_runs_to_del)
    print(f"Train run IDs to delete ({len(del_run_ids)}):", sorted(del_run_ids))

    # 1. Delete run directories from disk
    freed_bytes = 0
    deleted_dirs = []
    for rid in del_run_ids:
        for base in ["runs", "runs_curriculum"]:
            d = repo_root / base / rid
            if d.exists() and d.is_dir():
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                freed_bytes += size
                print(f"Removing directory: {d} ({size / (1024*1024):.2f} MB)")
                shutil.rmtree(d, onerror=_remove_readonly)
                deleted_dirs.append(str(d))

    print(f"Total disk space freed: {freed_bytes / (1024*1024):.2f} MB across {len(deleted_dirs)} directories.")

    # 2. Clean curriculum phase traceability files
    trace_path = reporting_dir / "curriculum_phase_traceability.jsonl"
    if trace_path.exists():
        lines = trace_path.read_text(encoding="utf-8").splitlines()
        kept_lines = []
        for line in lines:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if str(obj.get("train_run_id", "") or "") not in del_run_ids:
                    kept_lines.append(line)
            except Exception:
                kept_lines.append(line)
        trace_path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
        print(f"Updated {trace_path.name}: kept {len(kept_lines)} / {len(lines)} entries.")

    trace_latest = reporting_dir / "curriculum_phase_traceability.latest.json"
    if trace_latest.exists():
        try:
            obj = json.loads(trace_latest.read_text(encoding="utf-8"))
            if str(obj.get("train_run_id", "") or "") in del_run_ids:
                trace_latest.unlink()
                print("Removed stale curriculum_phase_traceability.latest.json")
        except Exception:
            pass

    # 3. Clean old parquet indexes to avoid upserting deleted models
    indexes_dir = reporting_dir / "indexes"
    if indexes_dir.exists():
        for pq in indexes_dir.glob("*.parquet"):
            try:
                pq.unlink()
                print(f"Removed old parquet index: {pq.name}")
            except Exception as e:
                print(f"Warning: could not remove {pq.name}: {e}")

    # 4. Re-publish catalog from surviving disk runs
    print("Re-publishing catalog snapshot...")
    pub_res = publish_catalog_snapshot(repo_root=repo_root)
    print("Catalog published successfully:", pub_res.get("catalog_mode", "ok"))

    # 5. Verification against duckdb
    con_check = duckdb.connect(str(duckdb_path))
    remaining_models = con_check.execute("SELECT engine, model_id, train_runs, eval_runs FROM catalog_models").fetchall()
    print("\n=== REMAINING MODELS IN DUCKDB ===")
    for m in remaining_models:
        print(f"Engine: {m[0]} | Model: {m[1]} | Trains: {m[2]} | Evals: {m[3]}")
    con_check.close()


if __name__ == "__main__":
    main()
