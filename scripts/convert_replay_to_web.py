import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def parse_hex(hex_str: str) -> Tuple[int, int]:
    """
    Convert '(q, r)' string into (q, r) tuple.
    """
    hex_str = hex_str.strip("()")
    q, r = hex_str.split(",")
    return int(q.strip()), int(r.strip())


# -------------------------------------------------
# Engine replay loading
# -------------------------------------------------

def load_engine_replay(path: Path) -> Dict:
    """
    Load a state-based engine replay JSON.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------
# Event inference
# -------------------------------------------------

def infer_events(prev_state: Dict, curr_state: Dict) -> List[Dict]:
    """
    Infer events by comparing two consecutive engine states.
    """
    events: List[Dict] = []

    prev_units = {u["unit_id"]: u for u in prev_state["units"]}
    curr_units = {u["unit_id"]: u for u in curr_state["units"]}

    for unit_id, curr_unit in curr_units.items():
        prev_unit = prev_units.get(unit_id)

        # Unit spawn
        if prev_unit is None:
            events.append({
                "event_type": "SPAWN",
                "unit_id": unit_id,
                "at": parse_hex(curr_unit["hex"]),
                "hp_after": curr_unit["strength"]
            })
            continue

        prev_hex = parse_hex(prev_unit["hex"])
        curr_hex = parse_hex(curr_unit["hex"])

        # Movement
        if prev_hex != curr_hex:
            events.append({
                "event_type": "MOVE",
                "unit_id": unit_id,
                "from": prev_hex,
                "to": curr_hex
            })

        # Damage
        if curr_unit["strength"] < prev_unit["strength"]:
            events.append({
                "event_type": "DAMAGE",
                "unit_id": unit_id,
                "amount": prev_unit["strength"] - curr_unit["strength"],
                "hp_after": curr_unit["strength"]
            })

        # Hold / no-op
        if prev_hex == curr_hex and curr_unit["strength"] == prev_unit["strength"]:
            events.append({
                "event_type": "HOLD",
                "unit_id": unit_id
            })

    return events


# -------------------------------------------------
# Conversion
# -------------------------------------------------

def convert_to_web_replay(engine_replay: Dict) -> Dict:
    """
    Convert engine state-based replay into web-friendly event replay.
    """
    web_replay = {
        "metadata": {
            "source": "engine_replay",
            "engine_version": engine_replay.get("version", 1)
        },
        "turns": []
    }

    states = engine_replay["states"]

    for i in range(1, len(states)):
        prev_state = states[i - 1]
        curr_state = states[i]

        events = infer_events(prev_state, curr_state)

        web_replay["turns"].append({
            "turn": curr_state["turn"],
            "events": events
        })

    return web_replay


# -------------------------------------------------
# CLI
# -------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print("  python -m scripts.convert_replay_to_web <engine_replay.json> <web_replay.json>")
        sys.exit(1)

    engine_path = Path(sys.argv[1])
    web_path = Path(sys.argv[2])

    engine_replay = load_engine_replay(engine_path)
    web_replay = convert_to_web_replay(engine_replay)

    with open(web_path, "w", encoding="utf-8") as f:
        json.dump(web_replay, f, indent=2)

    print(f"Web replay written to: {web_path}")


if __name__ == "__main__":
    main()