from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlops.contracts_v2 import SCHEMA_VERSION_V2


def _write_ndjson_zst(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    try:
        import zstandard as zstd  # type: ignore

        cctx = zstd.ZstdCompressor(level=3)
        path.write_bytes(cctx.compress(payload.encode("utf-8")))
    except Exception:
        # Keep extension stable for downstream contracts; fallback stores plain bytes.
        path.write_bytes(payload.encode("utf-8"))


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return False
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore

        table = pa.Table.from_pylist(rows)
        pq.write_table(table, path)
        return True
    except Exception:
        return False


def write_eval_bundle_v2(
    *,
    out_root: Path,
    eval_id: str,
    model_id: str,
    run_id: str,
    scenario_id: str,
    eval_decision_steps_top: list[dict[str, Any]],
    eval_decisions_top: list[dict[str, Any]],
    eval_decision_summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist strict v2 eval bundle optimized for viewer consumption.
    """
    # Storage key must be filesystem-safe across platforms (Windows forbids ':').
    eval_storage_id = str(eval_id).replace(":", "__")
    bundle_root = (out_root / "evals" / eval_storage_id).resolve()
    episodes_dir = bundle_root / "episodes"
    indexed_dir = bundle_root / "indexed"
    manifests_dir = bundle_root

    episode_id = "episode_0"
    step_rows = [dict(r or {}) for r in list(eval_decision_steps_top or [])]
    for idx, row in enumerate(step_rows):
        row.setdefault("step", int(idx))
        row.setdefault("schema_version", SCHEMA_VERSION_V2)
        row.setdefault("model_id", str(model_id))
        row.setdefault("eval_id", str(eval_id))
        row.setdefault("episode_id", episode_id)

    ndjson_path = episodes_dir / f"{episode_id}.ndjson.zst"
    _write_ndjson_zst(ndjson_path, step_rows)

    offsets = [{"step": int(i), "line": int(i)} for i, _ in enumerate(step_rows)]
    (episodes_dir / f"{episode_id}.index.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION_V2,
                "episode_id": episode_id,
                "rows": int(len(step_rows)),
                "offsets": offsets,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    parquet_ok = _write_parquet(indexed_dir / "decision_steps.parquet", step_rows)
    _write_parquet(indexed_dir / "decisions_top.parquet", [dict(x or {}) for x in list(eval_decisions_top or [])])

    manifest = {
        "schema_version": SCHEMA_VERSION_V2,
        "eval_id": str(eval_id),
        "eval_storage_id": str(eval_storage_id),
        "model_id": str(model_id),
        "run_id": str(run_id),
        "scenario_id": str(scenario_id),
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "episodes": [
            {
                "episode_id": episode_id,
                "rows": int(len(step_rows)),
                "ndjson_zst": str(ndjson_path.relative_to(bundle_root)).replace("\\", "/"),
                "index_json": str((episodes_dir / f"{episode_id}.index.json").relative_to(bundle_root)).replace("\\", "/"),
            }
        ],
        "indexed": {
            "decision_steps_parquet": parquet_ok,
        },
        "aggregates": {
            "eval_decision_summary": dict(eval_decision_summary or {}),
        },
    }
    (manifests_dir / "eval_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
