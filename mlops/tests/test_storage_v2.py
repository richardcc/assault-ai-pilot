from __future__ import annotations

import json
from pathlib import Path

from mlops.contracts_v2 import SCHEMA_VERSION_V2
from mlops.storage_v2 import write_eval_bundle_v2


def test_write_eval_bundle_v2_creates_manifest_and_episode_files(tmp_path: Path) -> None:
    manifest = write_eval_bundle_v2(
        out_root=tmp_path,
        eval_id="eval_1",
        model_id="model_1",
        run_id="run_1",
        scenario_id="scn_1",
        eval_decision_steps_top=[
            {
                "step": 0,
                "action_id": "WAIT:U1",
                "unit_id": "U1",
                "mcts_action_candidates": [],
            }
        ],
        eval_decisions_top=[],
        eval_decision_summary={"rows": 1},
    )
    assert manifest["schema_version"] == SCHEMA_VERSION_V2
    base = tmp_path / "evals" / "eval_1"
    assert (base / "eval_manifest.json").exists()
    assert (base / "episodes" / "episode_0.index.json").exists()
    idx = json.loads((base / "episodes" / "episode_0.index.json").read_text(encoding="utf-8"))
    assert idx["rows"] == 1
