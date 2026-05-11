import json
from pathlib import Path
from typing import List, Dict

RULE_CHUNKS_PATH = Path(
    "assault_rag/data/rulebook/chunks/rulebook_chunks.json"
)

def load_rule_chunks() -> List[Dict]:
    with open(RULE_CHUNKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def retrieve_rules_for_event(event: Dict, max_rules: int = 6) -> List[Dict]:
    """
    Recupera reglas relevantes para un evento de combate
    usando palabras clave deterministas.
    """
    rules = load_rule_chunks()
    keywords = set()

    # Palabras clave según evento
    if event["action"] == "RangedCombat":
        keywords.add("ranged")
        keywords.add("combat")

    if event.get("attack_sector"):
        keywords.add(event["attack_sector"].lower())

    if event.get("distance") is not None:
        keywords.add("range")

    matched = []
    for rule in rules:
        text_lower = rule["text"].lower()
        score = sum(1 for kw in keywords if kw in text_lower)

        if score > 0:
            matched.append((score, rule))

    # Ordenar por relevancia
    matched.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in matched[:max_rules]]