from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PerfThresholds:
    catalog_slim_max_bytes: int = 64 * 1024 * 1024
    catalog_slim_parse_max_ms: float = 1200.0
    duckdb_models_query_max_ms: float = 250.0
    duckdb_evals_query_max_ms: float = 350.0
    duckdb_trains_query_max_ms: float = 350.0


def _ms_since(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def measure_catalog_json(catalog_path: Path) -> dict[str, Any]:
    if not catalog_path.exists():
        return {"ok": False, "error": f"catalog not found: {catalog_path}"}
    size_bytes = int(catalog_path.stat().st_size)
    t0 = time.perf_counter()
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    parse_ms = _ms_since(t0)
    engines = len(list((payload or {}).get("engines", []) or [])) if isinstance(payload, dict) else 0
    return {
        "ok": True,
        "size_bytes": size_bytes,
        "parse_ms": float(parse_ms),
        "engines_count": int(engines),
    }


def measure_duckdb_queries(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"ok": False, "error": f"duckdb not found: {db_path}"}
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": f"duckdb import failed: {exc}"}

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        t0 = time.perf_counter()
        models_count = int(con.execute("SELECT COUNT(*) FROM catalog_models").fetchone()[0])
        models_ms = _ms_since(t0)

        t0 = time.perf_counter()
        evals_count = int(con.execute("SELECT COUNT(*) FROM catalog_evals").fetchone()[0])
        evals_ms = _ms_since(t0)

        t0 = time.perf_counter()
        trains_count = int(con.execute("SELECT COUNT(*) FROM catalog_trains").fetchone()[0])
        trains_ms = _ms_since(t0)
    except Exception as exc:
        return {"ok": False, "error": f"duckdb query failed: {exc}"}
    finally:
        con.close()

    return {
        "ok": True,
        "models_count": models_count,
        "evals_count": evals_count,
        "trains_count": trains_count,
        "models_query_ms": float(models_ms),
        "evals_query_ms": float(evals_ms),
        "trains_query_ms": float(trains_ms),
    }


def run_perf_gate(
    *,
    repo_root: Path,
    catalog_rel_path: str = "runs_curriculum/experiments/reporting/model_catalog_latest.json",
    duckdb_rel_path: str = "runs_curriculum/experiments/reporting/reporting.duckdb",
    thresholds: PerfThresholds | None = None,
) -> dict[str, Any]:
    th = thresholds or PerfThresholds()
    catalog_path = (repo_root / str(catalog_rel_path)).resolve()
    db_path = (repo_root / str(duckdb_rel_path)).resolve()
    catalog_metrics = measure_catalog_json(catalog_path)
    duckdb_metrics = measure_duckdb_queries(db_path)

    violations: list[str] = []
    if not catalog_metrics.get("ok"):
        violations.append(str(catalog_metrics.get("error", "catalog metrics failed")))
    else:
        if int(catalog_metrics.get("size_bytes", 0)) > int(th.catalog_slim_max_bytes):
            violations.append(
                f"catalog size exceeded: {catalog_metrics.get('size_bytes')} > {th.catalog_slim_max_bytes}"
            )
        if float(catalog_metrics.get("parse_ms", 0.0)) > float(th.catalog_slim_parse_max_ms):
            violations.append(
                f"catalog parse exceeded: {catalog_metrics.get('parse_ms'):.2f}ms > {th.catalog_slim_parse_max_ms:.2f}ms"
            )

    if not duckdb_metrics.get("ok"):
        violations.append(str(duckdb_metrics.get("error", "duckdb metrics failed")))
    else:
        if float(duckdb_metrics.get("models_query_ms", 0.0)) > float(th.duckdb_models_query_max_ms):
            violations.append(
                f"duckdb models query exceeded: {duckdb_metrics.get('models_query_ms'):.2f}ms > {th.duckdb_models_query_max_ms:.2f}ms"
            )
        if float(duckdb_metrics.get("evals_query_ms", 0.0)) > float(th.duckdb_evals_query_max_ms):
            violations.append(
                f"duckdb evals query exceeded: {duckdb_metrics.get('evals_query_ms'):.2f}ms > {th.duckdb_evals_query_max_ms:.2f}ms"
            )
        if float(duckdb_metrics.get("trains_query_ms", 0.0)) > float(th.duckdb_trains_query_max_ms):
            violations.append(
                f"duckdb trains query exceeded: {duckdb_metrics.get('trains_query_ms'):.2f}ms > {th.duckdb_trains_query_max_ms:.2f}ms"
            )

    return {
        "ok": len(violations) == 0,
        "repo_root": str(repo_root),
        "thresholds": asdict(th),
        "catalog_metrics": catalog_metrics,
        "duckdb_metrics": duckdb_metrics,
        "violations": violations,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run reporting persistence performance gate.")
    p.add_argument("--repo-root", default=".", help="Repository root.")
    p.add_argument(
        "--catalog",
        default="runs_curriculum/experiments/reporting/model_catalog_latest.json",
        help="Relative path to slim catalog JSON.",
    )
    p.add_argument(
        "--duckdb",
        default="runs_curriculum/experiments/reporting/reporting.duckdb",
        help="Relative path to reporting DuckDB.",
    )
    p.add_argument("--catalog-max-bytes", type=int, default=64 * 1024 * 1024)
    p.add_argument("--catalog-parse-max-ms", type=float, default=1200.0)
    p.add_argument("--duckdb-models-max-ms", type=float, default=250.0)
    p.add_argument("--duckdb-evals-max-ms", type=float, default=350.0)
    p.add_argument("--duckdb-trains-max-ms", type=float, default=350.0)
    return p


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    thresholds = PerfThresholds(
        catalog_slim_max_bytes=int(args.catalog_max_bytes),
        catalog_slim_parse_max_ms=float(args.catalog_parse_max_ms),
        duckdb_models_query_max_ms=float(args.duckdb_models_max_ms),
        duckdb_evals_query_max_ms=float(args.duckdb_evals_max_ms),
        duckdb_trains_query_max_ms=float(args.duckdb_trains_max_ms),
    )
    payload = run_perf_gate(
        repo_root=Path(args.repo_root).resolve(),
        catalog_rel_path=str(args.catalog),
        duckdb_rel_path=str(args.duckdb),
        thresholds=thresholds,
    )
    print(json.dumps(payload, indent=2))
    if not bool(payload.get("ok")):
        raise SystemExit(2)
