from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from mlops.contracts_v2 import SCHEMA_VERSION_V2
from mlops.reporting.build_catalog import build_reporting_catalog, merge_catalog_indexes_parquet
from mlops.reporting.catalog_duckdb import (
    build_catalog_duckdb_from_parquet,
    load_catalog_summary_from_duckdb,
)


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


@contextmanager
def _catalog_publish_lock(repo_root: Path, timeout_s: float = 30.0, poll_s: float = 0.1):
    lock_path = (repo_root / "runs_curriculum" / "experiments" / "reporting" / ".catalog_v2_publish.lock").resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    lock_fd = -1
    while True:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("utf-8"))
            break
        except FileExistsError:
            try:
                content = lock_path.read_text(encoding="utf-8").strip()
                owning_pid = int(content) if content.isdigit() else -1
                if owning_pid > 0 and not _is_pid_alive(owning_pid):
                    lock_path.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            if (time.monotonic() - start) >= float(timeout_s):
                try:
                    if (time.time() - lock_path.stat().st_mtime) >= float(timeout_s):
                        lock_path.unlink(missing_ok=True)
                        continue
                except Exception:
                    pass
                raise TimeoutError(f"timeout acquiring catalog publish lock: {lock_path}")
            time.sleep(float(poll_s))
    try:
        yield
    finally:
        try:
            if lock_fd >= 0:
                os.close(lock_fd)
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass


def _atomic_write_json(
    path: Path,
    payload: dict,
    *,
    retries: int = 6,
    retry_sleep_s: float = 0.12,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    last_exc: Exception | None = None
    body = json.dumps(payload, indent=2)
    for _ in range(max(1, int(retries))):
        try:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(path)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(float(retry_sleep_s))
        except OSError as exc:
            # Windows can surface sharing violations as generic OSError.
            last_exc = exc
            time.sleep(float(retry_sleep_s))
    if last_exc is not None:
        raise last_exc


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write_publish_status(path: Path, payload: dict) -> None:
    _atomic_write_json(path, dict(payload or {}))


def _prune_debug_catalog_history(debug_dir: Path, keep: int) -> list[str]:
    k = max(1, int(keep))
    rows = sorted(debug_dir.glob("model_catalog_full_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for p in rows[k:]:
        try:
            p.unlink()
            removed.append(str(p))
        except Exception:
            continue
    return removed


def publish_catalog_snapshot(
    *,
    repo_root: Path,
    catalog_rel_path: str = "runs_curriculum/experiments/reporting/model_catalog_latest.json",
    debug_full_catalog_rel_path: str = "runs_curriculum/experiments/reporting/model_catalog_full_latest.json",
    runs_roots_rel: Iterable[str] = ("runs_curriculum", "runs"),
    parquet_rel_dir: str = "runs_curriculum/experiments/reporting/indexes",
    max_eval_history_per_model_slim: int = 32,
    debug_full_history_keep: int = 12,
    include_debug_full_catalog: bool = True,
    incremental_run_ids: Iterable[str] | None = None,
) -> dict:
    with _catalog_publish_lock(repo_root=repo_root):
        reporting_dir = (repo_root / "runs_curriculum" / "experiments" / "reporting").resolve()
        reporting_dir.mkdir(parents=True, exist_ok=True)
        status_path = reporting_dir / "catalog_publish_status.json"
        status_payload = {
            "schema_version": SCHEMA_VERSION_V2,
            "status": "running",
            "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "phases": {},
            "errors": [],
        }
        _write_publish_status(status_path, status_payload)
        try:
            run_ids = {
                str(x or "").strip()
                for x in list(incremental_run_ids or [])
                if str(x or "").strip()
            }
            incremental_mode = bool(run_ids)
            payload = build_reporting_catalog(
                repo_root=repo_root,
                runs_roots_rel=runs_roots_rel,
                include_random_selfplay=False,
                # Parquet/DuckDB indexes must keep producer eval payload details
                # (seed_games/side_metrics) so ELO side-metric columns are populated.
                include_eval_payload_details=True,
                max_eval_history_per_model=max(1, int(max_eval_history_per_model_slim)),
                include_run_ids=(run_ids if incremental_mode else None),
            )
            payload = dict(payload or {})
            payload["schema_version"] = SCHEMA_VERSION_V2
            payload["catalog_mode"] = "producer_published_strict"
            payload["eval_history_limit_per_model"] = int(max(1, int(max_eval_history_per_model_slim)))
            if incremental_mode:
                status_payload["phases"]["incremental_run_ids"] = sorted(list(run_ids))
            out_catalog = (repo_root / str(catalog_rel_path)).resolve()

            out_debug_catalog = (repo_root / str(debug_full_catalog_rel_path)).resolve()
            if bool(include_debug_full_catalog):
                debug_full_catalog = build_reporting_catalog(
                    repo_root=repo_root,
                    runs_roots_rel=runs_roots_rel,
                    include_random_selfplay=False,
                    include_eval_payload_details=True,
                    max_eval_history_per_model=None,
                )
                debug_full_catalog = dict(debug_full_catalog or {})
                debug_full_catalog["schema_version"] = SCHEMA_VERSION_V2
                debug_full_catalog["catalog_mode"] = "producer_published_debug_full"
                debug_full_catalog["eval_history_limit_per_model"] = None
                _atomic_write_json(out_debug_catalog, debug_full_catalog)
                debug_hist = out_debug_catalog.parent / f"model_catalog_full_{_utc_stamp()}.json"
                _atomic_write_json(debug_hist, debug_full_catalog)
                removed = _prune_debug_catalog_history(out_debug_catalog.parent, keep=int(debug_full_history_keep))
                status_payload["phases"]["debug_catalog_written"] = True
                status_payload["phases"]["debug_catalog_pruned"] = {
                    "keep": int(max(1, int(debug_full_history_keep))),
                    "removed": removed,
                }
            else:
                status_payload["phases"]["debug_catalog_written"] = "skipped_incremental_mode"
            _write_publish_status(status_path, status_payload)

            index_out = merge_catalog_indexes_parquet(payload, (repo_root / str(parquet_rel_dir)).resolve())
            status_payload["phases"]["parquet_indexes_written"] = index_out
            _write_publish_status(status_path, status_payload)
            duckdb_out = build_catalog_duckdb_from_parquet(
                repo_root=repo_root,
                parquet_rel_dir=parquet_rel_dir,
            )
            status_payload["phases"]["duckdb_materialized"] = duckdb_out
            if bool(incremental_mode):
                slim_payload = load_catalog_summary_from_duckdb(repo_root=repo_root)
                slim_payload = dict(slim_payload or {})
                slim_payload["schema_version"] = SCHEMA_VERSION_V2
                slim_payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                )
                slim_payload["catalog_mode"] = "duckdb_primary_incremental"
                slim_payload["eval_history_limit_per_model"] = int(
                    max(1, int(max_eval_history_per_model_slim))
                )
                slim_payload["repo_root"] = str(repo_root)
                slim_payload["runs_roots"] = [str(x) for x in list(runs_roots_rel or []) if str(x)]
                _atomic_write_json(out_catalog, slim_payload)
            else:
                _atomic_write_json(out_catalog, payload)
            status_payload["phases"]["slim_catalog_written"] = True
            if not bool(duckdb_out.get("ok")):
                status_payload["errors"].append(str(duckdb_out.get("error", "duckdb materialization failed")))
            status_payload["status"] = "complete" if not status_payload["errors"] else "partial"
            status_payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write_publish_status(status_path, status_payload)
            return {
                "schema_version": SCHEMA_VERSION_V2,
                "catalog_path": str(out_catalog),
                "debug_catalog_path": str(out_debug_catalog),
                "index_summary": index_out,
                "duckdb_summary": duckdb_out,
                "publish_status_path": str(status_path),
                "publish_status": status_payload["status"],
            }
        except Exception as exc:
            status_payload["status"] = "failed"
            status_payload["errors"].append(str(exc))
            status_payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write_publish_status(status_path, status_payload)
            raise


def publish_train_run(*, repo_root: Path, run_id: str = "") -> dict:
    rid = str(run_id or "").strip()
    return publish_catalog_snapshot(
        repo_root=repo_root,
        include_debug_full_catalog=False,
        incremental_run_ids=([rid] if rid else None),
    )


def publish_eval_run(*, repo_root: Path, run_id: str = "") -> dict:
    rid = str(run_id or "").strip()
    return publish_catalog_snapshot(
        repo_root=repo_root,
        include_debug_full_catalog=False,
        incremental_run_ids=([rid] if rid else None),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish reporting catalog snapshot (JSON + Parquet + DuckDB)."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--max-eval-history-per-model-slim",
        type=int,
        default=32,
        help="Max eval history rows per model in slim catalog.",
    )
    parser.add_argument(
        "--debug-full-history-keep",
        type=int,
        default=12,
        help="How many debug full catalog snapshots to keep.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    out = publish_catalog_snapshot(
        repo_root=repo_root,
        max_eval_history_per_model_slim=max(1, int(args.max_eval_history_per_model_slim)),
        debug_full_history_keep=max(1, int(args.debug_full_history_keep)),
    )
    print(json.dumps(out, indent=2))
