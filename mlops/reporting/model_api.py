from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

_TRAIN_SUMMARY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _load_from_duckdb(repo_root: Path, run_id: str) -> dict[str, Any] | None:
    db_path = (repo_root / "runs_curriculum" / "experiments" / "reporting" / "reporting.duckdb").resolve()
    if not db_path.exists():
        return None
    try:
        import duckdb  # type: ignore

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            row = con.execute(
                """
                SELECT summary_json, observation_channels_json, channel_effectiveness_json
                FROM catalog_trains
                WHERE run_id = ?
                LIMIT 1
                """,
                [run_id],
            ).fetchone()
            if row and row[0]:
                payload = json.loads(str(row[0]))
                if isinstance(payload, dict):
                    if row[1]:
                        try:
                            payload["observation_channels"] = json.loads(str(row[1]))
                        except Exception:
                            pass
                    if row[2]:
                        try:
                            payload["channel_effectiveness"] = json.loads(str(row[2]))
                        except Exception:
                            pass
                    return payload
        finally:
            con.close()
    except Exception:
        pass
    return None


_DETECTED_HEADS_CACHE: dict[str, list[str]] = {}


def _detect_heads_from_run(repo_root: Path, rid: str) -> list[str]:
    if rid in _DETECTED_HEADS_CACHE:
        return list(_DETECTED_HEADS_CACHE[rid])
    candidates = [
        repo_root / "runs_curriculum" / rid,
        repo_root / "runs" / rid,
        repo_root / "runs_curriculum" / "experiments" / rid,
    ]
    for d in candidates:
        ckpt_dir = d / "checkpoints"
        if not ckpt_dir.exists():
            continue
        pt_files = sorted(ckpt_dir.glob("*.pt"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not pt_files:
            continue
        try:
            import torch  # type: ignore

            sd = torch.load(pt_files[0], map_location="cpu", weights_only=False)
            weights = sd.get("network", sd.get("model", sd))
            if isinstance(weights, dict):
                heads: list[str] = []
                for k in weights.keys():
                    for h in ["threat_map", "attrition", "morale", "intent", "multi_vp"]:
                        if h in k and h not in heads:
                            heads.append(h)
                _DETECTED_HEADS_CACHE[rid] = heads
                return list(heads)
        except Exception:
            pass
    _DETECTED_HEADS_CACHE[rid] = []
    return []


def build_train_summary_payload(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    run_id: str,
    load_catalog_payload: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rid = str(run_id or "").strip()
    if not rid:
        return {}

    # 1. Try DuckDB fast query
    db_payload = _load_from_duckdb(repo_root, rid)
    if db_payload:
        db_payload["heads_detected"] = _detect_heads_from_run(repo_root, rid)
        return db_payload

    # 2. Check direct candidates first to avoid loading 800MB catalog JSON
    candidate_roots = [
        "runs_curriculum/experiments",
        "runs_curriculum",
        "runs",
    ]
    runs_roots: list[str] = []
    for cr in candidate_roots:
        if (repo_root / cr / rid / "metrics" / "summary.json").exists():
            runs_roots = [cr]
            break

    # If not found directly, query catalog_payload as fallback
    if not runs_roots and load_catalog_payload is not None:
        try:
            catalog_payload = load_catalog_payload(repo_root=repo_root, catalog_rel_path=catalog_rel_path)
            runs_roots = list(catalog_payload.get("runs_roots", []) or [])
        except Exception:
            runs_roots = []

    if not runs_roots:
        runs_roots = candidate_roots

    for runs_root_rel in runs_roots:
        metrics_dir = (repo_root / str(runs_root_rel) / rid / "metrics").resolve()
        p = (metrics_dir / "summary.json").resolve()
        if not p.exists():
            continue

        mtime = p.stat().st_mtime
        cache_key = f"{runs_root_rel}/{rid}"
        cached = _TRAIN_SUMMARY_CACHE.get(cache_key)
        if cached and cached[0] == mtime:
            return dict(cached[1])

        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        obs_path = (metrics_dir / "observation_channels.json").resolve()
        obs_payload: dict[str, Any] = {}
        if obs_path.exists():
            try:
                loaded_obs = json.loads(obs_path.read_text(encoding="utf-8"))
                if isinstance(loaded_obs, dict):
                    obs_payload = dict(loaded_obs)
            except Exception:
                obs_payload = {}
        payload["observation_channels"] = obs_payload

        eff_path = (metrics_dir / "channel_effectiveness_report.json").resolve()
        eff_payload: dict[str, Any] = {}
        if eff_path.exists():
            try:
                loaded_eff = json.loads(eff_path.read_text(encoding="utf-8"))
                if isinstance(loaded_eff, dict):
                    eff_payload = dict(loaded_eff)
            except Exception:
                eff_payload = {}
        payload["channel_effectiveness"] = eff_payload
        payload["heads_detected"] = _detect_heads_from_run(repo_root, rid)

        _TRAIN_SUMMARY_CACHE[cache_key] = (mtime, dict(payload))
        return payload

    return {}

