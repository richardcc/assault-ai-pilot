import json
from assault.replay.deserialization import replay_from_dict

def load_replay_from_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return replay_from_dict(data)
