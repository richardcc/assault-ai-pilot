import json
from pathlib import Path

from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.dice_color import DiceColor


class FortificationConfig:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = (
                Path(__file__).resolve().parents[2]
                / "assault_sim"
                / "assets"
                / "rules_tables"
                / "fortification"
                / "fortification_modifiers.v1.json"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def _entry(self, fort_type: str):
        return self.data.get("fortifications", {}).get(fort_type, {})

    def get_defense_bonus(self, fort_type: str | None, unit_category: str, sector: AttackSector):
        if not fort_type:
            return []
        by_category = self._entry(fort_type).get("defense_bonus", {})
        by_sector = by_category.get(unit_category, {})
        names = by_sector.get(sector.name, [])
        result = []
        for name in names:
            normalized = str(name).strip().upper()
            if normalized in DiceColor.__members__:
                result.append(DiceColor[normalized])
        return result

    def apply_movement_delta(self, fort_type: str | None, move_type: str, base_cost: int | None):
        if base_cost is None or not fort_type:
            return base_cost
        delta_map = self._entry(fort_type).get("movement_delta", {})
        delta = delta_map.get(move_type, 0)
        if delta is None:
            return None
        return base_cost + int(delta)


fortification_config = FortificationConfig()
