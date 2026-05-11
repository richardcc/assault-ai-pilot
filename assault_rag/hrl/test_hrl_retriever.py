import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HRL_PRINCIPLES_PATH = BASE_DIR.parent / "knowledge" / "hrl_principles.json"


def load_hrl_principles():
    with open(HRL_PRINCIPLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def retrieve_hrl_principles(hrl_decision):
    principles = load_hrl_principles()
    # lógica existente de filtrado
    return principles
