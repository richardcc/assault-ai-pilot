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
        self._compile_attack_tables()

    def _compile_attack_tables(self) -> None:
        """Precompile raw attack dictionary into fast integer tuples."""
        compiled = {}
        mode_ranges = {}
        for mode, targets in (self._attack_raw or {}).items():
            mode_ranges[mode] = []
            for target_type, table in (targets or {}).items():
                bands = []
                for key, value in (table or {}).items():
                    if "-" in str(key):
                        parts = str(key).split("-")
                        start, end = int(parts[0]), int(parts[1])
                    else:
                        start = end = int(key)
                    mode_ranges[mode].append((start, end))
                    dice_colors = [DiceColor[d] for d in value.get("dice", [])] if isinstance(value, dict) else []
                    bands.append((start, end, dice_colors))
                compiled[(mode, target_type)] = bands
        self._compiled_attacks = compiled
        self._mode_ranges = mode_ranges

    # =================================================
    # ✅ MODE RESOLUTION (Optimized integer lookups)
    # =================================================
    def _resolve_attack_mode(self, distance: int) -> str | None:
        """
        Decide which attack mode to use based on compiled attack tables.
        """
        traits_u = {str(t).upper() for t in (self.traits or [])}
        classification_u = str(self.classification or "").upper()
        prefer_indirect = (
            "REMOVE_WEAKEST_TERRAIN_DEFENSE" in traits_u
            or "NO_LINE_OF_SIGHT" in traits_u
            or "INDIRECT_FIRE_UNIT" in classification_u
        )
        if prefer_indirect:
            for start, end in self._mode_ranges.get("INDIRECT_FIRE", []):
                if start <= distance <= end:
                    return "INDIRECT_FIRE"

        for mode, ranges in self._mode_ranges.items():
            for start, end in ranges:
                if start <= distance <= end:
                    return mode

        return None

    def has_attack_against(self, distance: int, target_category: UnitCategory) -> bool:
        """Fast check if weapon has an active profile against target at distance."""
        cat_val = target_category.value if hasattr(target_category, "value") else str(target_category)
        for mode in self._mode_ranges.keys():
            for start, end, _ in self._compiled_attacks.get((mode, cat_val), []):
                if start <= distance <= end:
                    return True
        return False

    # =================================================
    # ✅ CORE FUNCTION (Zero string parsing)
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
            if not mode:
                return []

            _trace("ATTACK_MODE", unit=self.code, mode=mode, dist=distance)

            cat_val = target_category.value if hasattr(target_category, "value") else str(target_category)
            for start, end, dice in self._compiled_attacks.get((mode, cat_val), []):
                if start <= distance <= end:
                    return list(dice)

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
