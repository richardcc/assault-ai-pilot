from typing import Dict, List
from enum import Enum
import os

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.attack_sector import AttackSector


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class UnitSide(Enum):
    GE = "GE"
    US = "US"


class UnitCategory(Enum):
    INFANTRY = "INFANTRY"
    VEHICLE = "VEHICLE"


class UnitType:
    """
    Canonical unit type definition.
    """

    def __init__(
        self,
        code: str,
        side: UnitSide,
        category: UnitCategory,
        subtype: str,
        classification: str,
        cost: int,
        movement: int,
        max_strength: int,
        base_defense: Dict[str, List[str]],
        attack: Dict[str, Dict[str, Dict[str, List[str]]]],
        traits: List[str],
    ) -> None:
        self.code = code
        self.side = side
        self.category = category
        self.subtype = subtype
        self.classification = classification
        self.cost = cost
        self.movement = movement
        self.max_strength = max_strength

        self._base_defense_raw = base_defense
        self._attack_raw = attack
        self.traits = traits

    # =================================================
    # CLOSE COMBAT API
    # =================================================

    def get_close_combat_attack_dice(
        self, target_category: UnitCategory
    ) -> List[DiceColor]:
        try:
            dice = self._attack_raw[target_category.value]["0"]["dice"]
            return [DiceColor[d] for d in dice]
        except Exception:
            return []

    def get_close_combat_defense_dice(
        self, sector: AttackSector
    ) -> List[DiceColor]:
        try:
            dice = self._base_defense_raw[sector.name]
            return [DiceColor[d] for d in dice]
        except Exception:
            return []