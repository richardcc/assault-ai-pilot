import json
from pathlib import Path
from typing import Dict, List

# -------------------------------------------------
# Paths (robust, independent of working directory)
# -------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
HRL_PRINCIPLES_PATH = BASE_DIR.parent / "knowledge" / "hrl_principles.json"

# -------------------------------------------------
# Load HRL principles
# -------------------------------------------------

def load_hrl_principles() -> List[Dict]:
    """
    Load strategic HRL principles from JSON file.
    """
    with open(HRL_PRINCIPLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# -------------------------------------------------
# Principle retrieval (backend-driven)
# -------------------------------------------------

def retrieve_hrl_principles(
    event: Dict,
    max_principles: int = 3
) -> List[Dict]:
    """
    Retrieve strategic HRL principles relevant to a backend
    activation context.

    Expected event format (backend context):
    {
        unit_id,
        action,
        friendly_strength,
        enemy_pressure,
        objective_distance
    }
    """

    principles = load_hrl_principles()

    enemy_pressure = event.get("enemy_pressure")
    friendly_strength = event.get("friendly_strength")
    objective_distance = event.get("objective_distance")

    scored: List[tuple[int, Dict]] = []

    for p in principles:
        tags = set(p.get("tags", []))
        score = 0

        if enemy_pressure and f"PRESSURE_{enemy_pressure}" in tags:
            score += 1

        if friendly_strength and f"STRENGTH_{friendly_strength}" in tags:
            score += 1

        if (
            objective_distance
            and objective_distance != "UNKNOWN"
            and f"OBJECTIVE_{objective_distance}" in tags
        ):
            score += 1

        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [p for _, p in scored[:max_principles]]