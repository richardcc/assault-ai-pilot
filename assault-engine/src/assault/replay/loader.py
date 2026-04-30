import json
from assault.replay.deserialization import replay_from_dict


def load_replay_from_json(path: str):
    """
    Load a replay from a JSON file.

    Notes:
    - The JSON may contain both world state snapshots
      and SYSTEM EVENT entries (END_TURN, END_MATCH).
    - Interpretation is delegated to replay_from_dict.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return replay_from_dict(data)