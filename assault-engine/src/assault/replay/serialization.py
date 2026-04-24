import json
from assault.replay.state import ReplayState, UnitState


def replay_state_to_dict(state: ReplayState) -> dict:
    """
    Convert a single ReplayState to a JSON-serializable dict.
    """
    return {
        "turn": state.turn,
        "units": [
            {
                "unit_id": unit.unit_id,
                "side": unit.side,
                "hex": unit.hex,
                "strength": unit.strength,
                "status": unit.status,  # list[str]
            }
            for unit in state.units
        ],
    }


def replay_to_dict(replay) -> dict:
    """
    Convert a Replay object to a JSON-serializable dict.
    """
    return {
        "version": 1,
        "states": [
            replay_state_to_dict(state)
            for state in replay.states
        ],
    }


def save_replay_to_json(replay, file_path: str):
    """
    Save Replay object to a JSON file.
    """
    data = replay_to_dict(replay)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)