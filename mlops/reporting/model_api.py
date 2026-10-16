from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def build_train_summary_payload(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    run_id: str,
    load_catalog_payload: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    rid = str(run_id or "").strip()
    if not rid:
        return {}
    catalog_payload = load_catalog_payload(repo_root=repo_root, catalog_rel_path=catalog_rel_path)
    runs_roots = list(catalog_payload.get("runs_roots", []) or [])
    if not runs_roots:
        return {"error": "runs_roots missing in strict catalog"}
    for runs_root_rel in runs_roots:
        metrics_dir = (repo_root / str(runs_root_rel) / rid / "metrics").resolve()
        p = (metrics_dir / "summary.json").resolve()
        if not p.exists():
            continue
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
        return payload
    return {}
