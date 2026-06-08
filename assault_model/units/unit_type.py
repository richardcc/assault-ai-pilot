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
    IT = "IT"


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
        attack: Dict,
        traits: List[str],
        movement_type: str = "foot",
    ) -> None:
        self.code = code
        self.side = side
        self.category = category
        self.subtype = subtype
        self.classification = classification
        self.cost = cost
        self.movement = movement
        # Movement type for terrain cost lookup (foot / artillery / wheeled / track).
        self.movement_type = movement_type
        self.max_strength = max_strength

        self._base_defense_raw = base_defense
        self._attack_raw = attack
        self.traits = traits

    # =================================================
    # ✅ NEW: MODE RESOLUTION
    # =================================================
    def _resolve_attack_mode(self, distance: int) -> str | None:
        """
        Decide which attack mode to use based on actual attack tables.
        """
        def _mode_has_distance(mode_name: str) -> bool:
            mode_payload = self._attack_raw.get(mode_name, {}) or {}
            for table in mode_payload.values():
                for key in table.keys():
                    if "-" in key:
                        start, end = map(int, key.split("-"))
                        if start <= distance <= end:
                            return True
                    else:
                        if int(key) == distance:
                            return True
            return False

        # Rifle-grenade style units should prefer indirect profile when available
        # at the same range band, so indirect-only effects are applied correctly.
        traits_u = {str(t).upper() for t in (self.traits or [])}
        classification_u = str(self.classification or "").upper()
        prefer_indirect = (
            "REMOVE_WEAKEST_TERRAIN_DEFENSE" in traits_u
            or "NO_LINE_OF_SIGHT" in traits_u
            or "INDIRECT_FIRE_UNIT" in classification_u
        )
        if prefer_indirect and _mode_has_distance("INDIRECT_FIRE"):
            return "INDIRECT_FIRE"

        for mode, targets in self._attack_raw.items():

            for target_type, table in targets.items():

                for key in table.keys():

                    if "-" in key:
                        start, end = map(int, key.split("-"))

                        if start <= distance <= end:
                            return mode

                    else:
                        if int(key) == distance:
                            return mode

        return None
    

    # =================================================
    # ✅ NEW CORE FUNCTION (replaces old logic)
    # =================================================
    def get_attack_dice(
        self,
        distance: int,
        target_category: UnitCategory,
    ) -> List[DiceColor]:
        """
        Return attack dice given distance and target type.
        Supports multiple attack modes (DIRECT / INDIRECT).
        """

        try:
            mode = self._resolve_attack_mode(distance)

            _trace("ATTACK_MODE", unit=self.code, mode=mode, dist=distance)

            attack_mode = self._attack_raw.get(mode, {})
            target_table = attack_mode.get(target_category.value, {})

            # Iterate range bands
            for key, value in target_table.items():

                if "-" in key:
                    start, end = map(int, key.split("-"))
                    if start <= distance <= end:
                        return [DiceColor[d] for d in value["dice"]]

                else:
                    if int(key) == distance:
                        return [DiceColor[d] for d in value["dice"]]

        except Exception as e:
            _trace("ATTACK_ERROR", error=str(e), unit=self.code)

        return []

    # =================================================
    # CLOSE COMBAT
    # =================================================
    def get_close_combat_attack_dice(
        self,
        target_category: UnitCategory,
    ) -> List[DiceColor]:
        return self.get_attack_dice(
            distance=0,
            target_category=target_category,
        )

    # =================================================
    # DEFENSE
    # =================================================
    def get_defense_dice(
        self,
        sector: AttackSector,
    ) -> List[DiceColor]:
        try:
            dice = self._base_defense_raw[sector.name]
            return [DiceColor[d] for d in dice]
        except Exception:
            return []
