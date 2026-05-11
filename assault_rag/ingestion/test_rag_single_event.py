import json
import os
from typing import List, Dict, Optional

# ============================================================
# CONFIGURACIÓN
# ============================================================

REPLAY_PATH = (
    "assault_rag/data/replays/raw/"
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
)

TEST_EVENT_QUERY = {
    "turn": 4,
    "attacker": "US_2",
    "defender": "GE_2",
    "action": "RangedCombat"
}

# Reglas hard-coded por ahora (se sustituirán luego por PDF)
HARDCODED_RULES = """
Rule 10.7 – Resolving Combat:
Attacks are resolved by rolling attack dice against defense dice.

Rule 10.9.3 – Areas of Impact:
Rear attacks reduce defender dice effectiveness.

Rule 10.1 – Range:
Ranged attacks are allowed at distance 3.
"""

# ============================================================
# CARGA DEL REPLAY
# ============================================================

def load_replay(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ============================================================
# EXTRACCIÓN DE COMBATES (ACTION_EFFECT)
# ============================================================

def extract_combat_events(replay: Dict) -> List[Dict]:
    events = []

    for turn in replay.get("turns", []):
        turn_number = turn["turn"]

        for ev in turn.get("events", []):
            if ev.get("type") != "ACTION_EFFECT":
                continue

            payload = ev.get("payload", {})
            if payload.get("action") != "RangedCombat":
                continue

            events.append({
                "turn": turn_number,
                "action": payload["action"],
                "attacker": payload["attacker"],
                "defender": payload["defender"],
                "distance": payload.get("distance"),
                "attack_sector": payload.get("attack_sector"),
                "hp_before": payload.get("defender_hp_before"),
                "hp_after": payload.get("defender_hp_after"),
                "raw": payload
            })

    return events

# ============================================================
# BÚSQUEDA DE EVENTO
# ============================================================

def find_event(events: List[Dict], query: Dict) -> Optional[Dict]:
    for ev in events:
        if (
            ev["turn"] == query["turn"]
            and ev["attacker"] == query["attacker"]
            and ev["defender"] == query["defender"]
            and ev["action"] == query["action"]
        ):
            return ev
    return None

# ============================================================
# CONTEXTO Y PROMPT
# ============================================================

def build_event_context(event: Dict) -> str:
    return (
        f"Turn {event['turn']}:\n"
        f"{event['attacker']} performed a ranged attack against "
        f"{event['defender']} at distance {event['distance']} "
        f"from the {event['attack_sector']} sector.\n"
        f"Defender HP: {event['hp_before']} → {event['hp_after']}."
    )

def build_prompt(context: str, rules: str) -> str:
    return f"""
You are an expert Assault rules analyst.

Event:
{context}

Relevant Rules:
{rules}

Explain step by step why this combat action was legal and effective
according to the rules. Cite rule numbers explicitly.
""".strip()

# ============================================================
# LLAMADA AL LLM
# ============================================================

def call_llm(prompt: str) -> str:
    """
    Requiere variable de entorno:
    OPENAI_API_KEY
    """
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # puedes cambiarlo
        messages=[
            {"role": "system", "content": "You explain tabletop wargame rules accurately."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content

# ============================================================
# MAIN
# ============================================================

def main():
    print("▶ Loading replay...")
    replay = load_replay(REPLAY_PATH)

    print("▶ Extracting combat events...")
    events = extract_combat_events(replay)
    print(f"  Found {len(events)} ranged combat events.")

    print("▶ Searching for target event...")
    event = find_event(events, TEST_EVENT_QUERY)

    if not event:
        print("❌ Event not found.")
        return

    context = build_event_context(event)
    prompt = build_prompt(context, HARDCODED_RULES)

    print("\n▶ Calling LLM...\n")
    explanation = call_llm(prompt)

    print("\n================ LLM EXPLANATION ================\n")
    print(explanation)
    print("\n=================================================\n")

if __name__ == "__main__":
    main()