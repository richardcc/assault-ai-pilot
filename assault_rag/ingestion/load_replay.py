import json

REPLAY_PATH = (
    "assault_rag/data/replays/raw/"
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
)

def load_replay():
    with open(REPLAY_PATH, "r", encoding="utf-8") as f:
        replay = json.load(f)
    return replay