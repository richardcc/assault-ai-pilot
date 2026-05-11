import json
from pathlib import Path
from typing import Dict, List

# =========================================================
# MANUAL HP ASSIGNMENT WHITELIST
# =========================================================
# Reglas que, por diseño del sistema, asignan daño real a HP
# aunque el texto no lo diga explícitamente en lenguaje natural.

HP_ASSIGNMENT_RULE_PREFIXES = [
    "10.7",  # Resolving Ranged Combat
    "10.9",  # Defense Dice and Cancellation
]

INPUT_PATH = Path(
    "assault_rag/data/rulebook/chunks/rulebook_chunks.json"
)

OUTPUT_PATH = Path(
    "assault_rag/data/rulebook/typed/rulebook_typed.json"
)

def infer_tags(rule_id: str, text: str) -> Dict:
    text_l = text.lower()

    tags = {
        "applies_to": [],
        "concerns": [],
        "unit_types": [],
        "phase": None,
    }

    # =========================================================
    # EVENT TYPE
    # =========================================================
    if rule_id.startswith("10"):
        tags["applies_to"].append("RANGED_COMBAT")

    # =========================================================
    # PHASE — LEGALITY (primero)
    # =========================================================
    if any(k in text_l for k in [
        "line of sight",
        "los",
        "spot",
        "spotting",
        "arc of fire",
        "firing blind",
        "range "
    ]):
        tags["phase"] = "LEGALITY"

    # =========================================================
    # PHASE — RESOLUTION (solo si hay evidencia REAL)
    # =========================================================
    if any(k in text_l for k in [
        "assign damage",
        "assigning damage",
        "uncancelled damage",
        "remaining damage",
        "damage is assigned",
        "critical hits are applied",
        "remaining criticals",
        "remove hp",
        "hp is reduced",
        "defender hp"
    ]):
        tags["phase"] = "RESOLUTION"

    # Default seguro
    if tags["phase"] is None:
        tags["phase"] = "LEGALITY"

    # =========================================================
    # CONCERNS (qué mecánica explica la regla)
    # =========================================================

    if any(k in text_l for k in ["rear", "flank", "front"]):
        tags["concerns"].append("IMPACT_SECTOR")

    if any(k in text_l for k in ["cancel", "compare dice"]):
        tags["concerns"].append("DICE_RESOLUTION")

    if any(k in text_l for k in [
        "assign damage",
        "assigning damage",
        "uncancelled damage",
        "remaining damage",
        "critical hits"
    ]):
        tags["concerns"].append("DAMAGE_ASSIGNMENT")

    if "defense dice" in text_l:
        tags["concerns"].append("DEFENSE_MODIFIER")

    # =========================================================
    # UNIT TYPES
    # =========================================================

    if "infantry" in text_l:
        tags["unit_types"].append("INFANTRY")

    if any(k in text_l for k in ["vehicle", "transport", "armor"]):
        tags["unit_types"].append("VEHICLE")

    if not tags["unit_types"]:
        tags["unit_types"] = ["INFANTRY", "VEHICLE"]

    # =========================================================
    # EXPLICIT HP ASSIGNMENT — AUTORIDAD FINAL
    # =========================================================
    for prefix in HP_ASSIGNMENT_RULE_PREFIXES:
        if rule_id.startswith(prefix):
            if "HP_ASSIGNMENT" not in tags["concerns"]:
                tags["concerns"].append("HP_ASSIGNMENT")
            tags["phase"] = "RESOLUTION"

    return tags

def main():
    print("▶ Loading rulebook chunks...")
    rules = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    typed_rules: List[Dict] = []

    for rule in rules:
        tags = infer_tags(rule["rule_id"], rule["text"])

        typed_rules.append({
            "rule_id": rule["rule_id"],
            "text": rule["text"],
            "applies_to": tags["applies_to"],
            "phase": tags["phase"],
            "concerns": tags["concerns"],
            "unit_types": tags["unit_types"],
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(typed_rules, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"✅ Typed {len(typed_rules)} rules with phase")
    print(f"✅ Saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()