import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_timeline_export_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "timeline.json"
        cmd = [
            sys.executable,
            "-m",
            "voec_sim.ui_contract.export_timeline",
            "--voec-config",
            "voec_sim/configs/voec_config.yaml",
            "--scenario",
            "battaglia_cittadina_2_1",
            "--seed",
            "5",
            "--policy",
            "first",
            "--max-steps",
            "5",
            "--out",
            str(out),
        ]
        subprocess.check_call(cmd)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "v1"
        assert payload["scenario_id"] == "battaglia_cittadina_2_1"
        assert len(payload["transitions"]) >= 1
