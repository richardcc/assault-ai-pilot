from __future__ import annotations

import json
from pathlib import Path

from mlops.reporting.model_api import build_train_summary_payload


def test_build_train_summary_payload_includes_observation_channels(tmp_path: Path) -> None:
    repo_root = tmp_path
    rid = "efficientzero_v2_test1234"
    runs_root = repo_root / "runs_curriculum"
    metrics_dir = runs_root / rid / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "summary.json").write_text(json.dumps({"loss": 1.23}), encoding="utf-8")
    obs_payload = {
        "shape": {"channels": 32, "height": 16, "width": 16},
        "channels": [{"index": 0, "name": "ally_presence"}],
    }
    (metrics_dir / "observation_channels.json").write_text(
        json.dumps(obs_payload), encoding="utf-8"
    )

    payload = build_train_summary_payload(
        repo_root=repo_root,
        catalog_rel_path="ignored.json",
        run_id=rid,
        load_catalog_payload=lambda **_kwargs: {"runs_roots": ["runs_curriculum"]},
    )

    assert payload.get("loss", None) == 1.23
    obs = dict(payload.get("observation_channels", {}) or {})
    assert int(((obs.get("shape", {}) or {}).get("channels", 0) or 0)) == 32
    rows = list(obs.get("channels", []) or [])
    assert rows and str(rows[0].get("name", "")) == "ally_presence"
