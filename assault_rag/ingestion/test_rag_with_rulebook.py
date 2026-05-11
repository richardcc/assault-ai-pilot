import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

# ============================================================
# PATHS
# ============================================================

REPLAY_PATH = Path(
    "assault_sim/session/replays/"
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
)

RULEBOOK_TYPED_PATH = Path(
    "assault_rag/data/rulebook/typed/rulebook_typed.json"
)

# Evento de prueba
TEST_EVENT_QUERY = {
    "turn": 4,
    "attacker": "US_2",
    "defender": "GE_2",
    "action": "RangedCombat",
}

# ============================================================
# REPLAY → EVENTO (con HECHOS del combate)
# ============================================================

def load_replay() -> Dict:
    with open(REPLAY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_combat_events(replay: Dict) -> List[Dict]:
    events = []

    for turn in replay.get("turns", []):
        turn_no = turn["turn"]
        for ev in turn.get("events", []):
            if ev.get("type") == "ACTION_EFFECT":
                payload = ev.get("payload", {})
                if payload.get("action") == "RangedCombat":

                    features = [
                        "DICE_RESOLUTION",
                        "DAMAGE_ASSIGNMENT",
                        "HP_ASSIGNMENT",
                    ]

                    if payload.get("attack_sector") in [
                        "REAR", "FRONT", "FLANK_LEFT", "FLANK_RIGHT"
                    ]:
                        features.append("IMPACT_SECTOR")

                    # ✅ HECHOS OBSERVADOS DEL COMBATE
                    dice_context = {
                        "attacker_dice": payload.get("attacker_attack_dice", []),
                        "defender_dice": payload.get("defender_defense_dice", []),
                        "remaining_damage": payload.get("resolution", {}).get(
                            "remaining_damage", 0
                        ),
                        "remaining_criticals": payload.get("resolution", {}).get(
                            "remaining_criticals", 0
                        ),
                    }

                    events.append({
                        "event_type": "RANGED_COMBAT",
                        "unit_type": "INFANTRY",
                        "features": features,
                        "dice_context": dice_context,
                        "turn": turn_no,
                        "action": payload["action"],
                        "attacker": payload["attacker"],
                        "defender": payload["defender"],
                        "distance": payload.get("distance"),
                        "attack_sector": payload.get("attack_sector"),
                        "hp_before": payload.get("defender_hp_before"),
                        "hp_after": payload.get("defender_hp_after"),
                    })

    return events

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
# RULE SELECTOR CANÓNICO
# ============================================================

def load_typed_rules() -> List[Dict]:
    with open(RULEBOOK_TYPED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def select_rules_for_event(event: Dict, max_rules: int = 4) -> List[Dict]:
    rules = load_typed_rules()
    selected = []

    for rule in rules:
        if event["event_type"] not in rule["applies_to"]:
            continue
        if event["unit_type"] not in rule["unit_types"]:
            continue
        if rule["phase"] != "RESOLUTION":
            continue
        if not any(c in event["features"] for c in rule["concerns"]):
            continue

        selected.append(rule)

    # 🔒 Exigir asignación real de HP
    if not any("HP_ASSIGNMENT" in r["concerns"] for r in selected):
        return []

    selected.sort(key=lambda r: len(r["concerns"]), reverse=True)
    return selected[:max_rules]

# ============================================================
# PROMPT + LLM (con CONSTRAINTS duras)
# ============================================================

def build_prompt(event: Dict, rules: List[Dict]) -> str:
    rules_text = "\n\n".join(
        f"Rule {r['rule_id']}:\n{r['text']}" for r in rules
    )

    dice = event["dice_context"]

    return f"""
You are an expert analyst of the Assault ruleset.

Event:
Turn {event['turn']}:
{event['attacker']} performed a ranged attack against {event['defender']}
at distance {event['distance']} from the {event['attack_sector']} sector.
Defender HP changed from {event['hp_before']} to {event['hp_after']}.

Observed combat results:
- Attacker dice results: {dice['attacker_dice']}
- Defender dice results: {dice['defender_dice']}
- Uncancelled DAMAGE symbols: {dice['remaining_damage']}
- Uncancelled CRITICAL symbols: {dice['remaining_criticals']}

Relevant Rules (from the official rulebook):
{rules_text}

Important constraints (mandatory):
- Defense dice NEVER generate damage.
- Defense dice ONLY cancel attacker symbols.
- Only ATTACKER dice can generate DAMAGE, CRITICAL, or SUPPRESS effects.
- Damage assignment must match EXACTLY the observed results:
  - Uncancelled DAMAGE = {dice['remaining_damage']}
  - Uncancelled CRITICAL = {dice['remaining_criticals']}

Instructions:
- Use ONLY the rules provided.
- Cite exact rule numbers.
- Explain explicitly:
  1) How attack and defense dice were compared and canceled.
  2) How uncancelled symbols were assigned as damage.
  3) Why the {event['attack_sector']} attack sector mattered.
  4) Why HP changed from before to after.
- Do NOT mention LOS, spotting, arc of fire, activation phases, or vehicles.
- Do NOT invent mechanics or modifiers.

Explain why this combat action produced the observed result.
""".strip()

def call_llm(prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", "llama3:8b"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8"))

    return proc.stdout.decode("utf-8")

# ============================================================
# MAIN
# ============================================================

def main():
    print("▶ Loading replay...")
    replay = load_replay()

    print("▶ Extracting combat events...")
    events = extract_combat_events(replay)

    event = find_event(events, TEST_EVENT_QUERY)
    if not event:
        raise RuntimeError("Test event not found")

    print("✅ Combat event selected")

    print("▶ Selecting RESOLUTION rules...")
    rules = select_rules_for_event(event)

    if not rules:
        print("\n⚠️ No sufficient RESOLUTION rules to explain HP change honestly.")
        return

    print(f"✅ Selected {len(rules)} RESOLUTION rules")

    print("▶ Building prompt and calling LLM...")
    explanation = call_llm(build_prompt(event, rules))

    print("\n================ EXPLANATION ================\n")
    print(explanation)
    print("\n============================================\n")

if __name__ == "__main__":
    main()