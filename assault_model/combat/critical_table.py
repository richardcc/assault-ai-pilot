import json
from pathlib import Path

from assault_model.combat.unit_class import UnitClass
from assault_model.combat.critical_effect import CriticalEffect


def _load_critical_table():
    table_path = (
        Path(__file__).resolve().parents[2]
        / "assault_sim"
        / "assets"
        / "rules_tables"
        / "combat"
        / "critical_table.v1.json"
    )
    payload = json.loads(table_path.read_text(encoding="utf-8"))
    raw = payload.get("critical_effects", {})
    parsed = {}
    for unit_class_name, effect_name in raw.items():
        if unit_class_name not in UnitClass.__members__:
            continue
        if effect_name not in CriticalEffect.__members__:
            continue
        parsed[UnitClass[unit_class_name]] = CriticalEffect[effect_name]
    return parsed


CRITICAL_TABLE = _load_critical_table()
