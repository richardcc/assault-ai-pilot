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
    #  COMBAT API
    # =================================================

    def get_attack_dice(
        self,
        distance: int,
        target_category: UnitCategory,
    ) -> List[DiceColor]:
        """
        Return attack dice for a given target category at a given distance (hexes).
        distance=0 covers close combat.
        """

        # Translate distance -> card band key
        if distance == 0:
            band_key = "0"
        elif 1 <= distance <= 3:
            band_key = "1-3"
        elif 4 <= distance <= 7:
            band_key = "4-7"
        else:
            band_key = "8-10"

        try:
            dice = self._attack_raw[target_category.value][band_key]["dice"]
            return [DiceColor[d] for d in dice]
        except Exception:
            return []
        
    def get_close_combat_attack_dice(
        self, target_category: UnitCategory
    ) -> List[DiceColor]:
        # Close combat is simply distance = 0
        return self.get_attack_dice(
            distance=0,
            target_category=target_category,
        )        
    
    def get_defense_dice(
        self,
        sector: AttackSector,
    ) -> List[DiceColor]:
        """
        Return defense dice for a given attack sector.
        Used by BOTH close combat and ranged combat.
        """
        try:
            dice = self._base_defense_raw[sector.name]
            return [DiceColor[d] for d in dice]
        except Exception:
            return []