from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def build_v2_catalog_payload(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    requested_catalog_rel_path: str,
    load_catalog_summary_from_duckdb: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    try:
        payload = load_catalog_summary_from_duckdb(repo_root=repo_root)
    except Exception as exc:
        payload = {"error": f"duckdb busy or unavailable: {exc}", "engines": []}
    payload = dict(payload or {})
    payload["schema_version"] = "reporting_v2_strict"
    if str((payload or {}).get("error", "") or "").strip():
        payload["catalog_source"] = "duckdb_strict_error"
    else:
        payload["catalog_source"] = "duckdb"
    return payload


def build_publish_status_payload(repo_root: Path) -> tuple[dict[str, Any], int]:
    status_path = (repo_root / "runs_curriculum" / "experiments" / "reporting" / "catalog_publish_status.json").resolve()
    if not status_path.exists():
        return (
            {
                "schema_version": "reporting_v2_strict",
                "status": "missing",
                "error": f"publish status not found: {status_path}",
            },
            404,
        )
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return (
            {
                "schema_version": "reporting_v2_strict",
                "status": "invalid",
                "error": f"failed parsing publish status: {exc}",
            },
            500,
        )
    return (
        payload if isinstance(payload, dict) else {"schema_version": "reporting_v2_strict"},
        200,
    )


def build_v2_model_payload(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    engine: str,
    model_id: str,
    train_limit: int,
    eval_limit: int,
    load_model_detail_index_first: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    out = load_model_detail_index_first(
        repo_root=repo_root,
        catalog_rel_path=catalog_rel_path,
        engine=engine,
        model_id=model_id,
        train_limit=train_limit,
        eval_limit=eval_limit,
    )
    out = out if isinstance(out, dict) else {}
    out["schema_version"] = "reporting_v2_strict"
    return out


def build_v2_model_evals_payload(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    engine: str,
    model_id: str,
    offset: int,
    limit: int,
    train_run_id: str = "",
    scenario_id: str = "__all__",
    include_payload: bool = False,
    load_eval_history_page_from_parquet: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if load_eval_history_page_from_parquet is None:
        return {
            "schema_version": "reporting_v2_strict",
            "engine": engine,
            "model_id": model_id,
            "train_run_id": train_run_id,
            "scenario_id": scenario_id,
            "offset": int(max(0, offset)),
            "limit": int(max(1, limit)),
            "total": 0,
            "rows": [],
            "error": "load_eval_history_page_from_parquet is not configured",
        }
    idx = load_eval_history_page_from_parquet(
        repo_root=repo_root,
        engine=engine,
        model_id=model_id,
        offset=offset,
        limit=limit,
        train_run_id=train_run_id,
        scenario_id=scenario_id,
        include_payload=include_payload,
    )
    rows = list(idx.get("rows", []) or [])
    total = int(idx.get("total", 0) or 0)
    start = max(0, min(offset, total))
    out = {
        "schema_version": "reporting_v2_strict",
        "engine": engine,
        "model_id": model_id,
        "train_run_id": train_run_id,
        "scenario_id": scenario_id,
        "offset": int(start),
        "limit": int(limit),
        "total": int(total),
        "rows": rows,
    }
    if str(idx.get("error", "") or "").strip():
        out["error"] = str(idx.get("error", ""))
    return out


def build_v2_model_trains_payload(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    engine: str,
    model_id: str,
    offset: int,
    limit: int,
    load_train_history_page_from_duckdb: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    idx = load_train_history_page_from_duckdb(
        repo_root=repo_root,
        engine=engine,
        model_id=model_id,
        offset=offset,
        limit=limit,
    )
    rows = list(idx.get("rows", []) or [])
    total = int(idx.get("total", 0) or 0)
    start = max(0, min(offset, total))
    out = {
        "schema_version": "reporting_v2_strict",
        "engine": engine,
        "model_id": model_id,
        "offset": int(start),
        "limit": int(limit),
        "total": int(total),
        "rows": rows,
    }
    if str(idx.get("error", "") or "").strip():
        out["error"] = str(idx.get("error", ""))
    return out
