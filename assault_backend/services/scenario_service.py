import json
from pathlib import Path

SCENARIOS_PATH = (
    Path(__file__).resolve()
    .parents[2]
    / "assault_sim"
    / "assets"
    / "scenarios"
)

def load_scenario_raw(scenario_id: str) -> dict:
    """
    Load scenario JSON and return it AS-IS.
    No transformation, no inference.
    """
    path = SCENARIOS_PATH / f"{scenario_id}.json"

    if not path.exists():
        raise FileNotFoundError(scenario_id)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
