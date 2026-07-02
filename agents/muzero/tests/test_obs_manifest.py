import json
from pathlib import Path

from agents.muzero.obs.run_manifest import RunManifest


def test_run_manifest_writes_required_fields(tmp_path: Path):
    manifest = RunManifest(
        run_id="r1",
        scenario_id="battaglia_cittadina_2_1",
        seed=1,
        config={"iterations": 1},
    )
    out = tmp_path / "manifest.json"
    manifest.write(out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
    assert payload["scenario_id"] == "battaglia_cittadina_2_1"
