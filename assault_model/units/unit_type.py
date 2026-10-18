from typing import Dict, List, Optional, Tuple
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
    UK = "UK"


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
        subtype: str = "",
        classification: str = "",
        cost: int = 0,
        movement: int = 0,
        max_strength: int = 1,
        base_defense: Dict[str, List[str]] = None,
        attack: Dict = None,
        traits: List[str] = None,
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
        self.smoke_profile = None

        for mode, targets in (self._attack_raw or {}).items():
            if mode == "SMOKE":
                if isinstance(targets, dict):
                    if "dice" in targets:
                        self.smoke_profile = {
                            "target_hex": targets.get("target_hex", True),
                            "max_adjacent_hexes": int(targets.get("max_adjacent_hexes", 2)),
                            "dice": [DiceColor[d] for d in targets.get("dice", []) if d in DiceColor.__members__]
                        }
                    elif "SMOKE_TARGET" in targets:
                        st = targets["SMOKE_TARGET"]
                        for r_key, r_val in st.items():
                            self.smoke_profile = {
                                "target_hex": True,
                                "max_adjacent_hexes": 2,
                                "dice": [DiceColor[d] for d in r_val.get("dice", []) if d in DiceColor.__members__]
                            }
                continue

            mode_ranges[mode] = []
            if not isinstance(targets, dict):
                continue

            # Check if this mode defines ranges directly (targetless hex/area fire)
            is_direct_range_table = any(
                isinstance(v, dict) and "dice" in v for k, v in targets.items()
            )

            if is_direct_range_table:
                bands = []
                for key, value in targets.items():
                    if not isinstance(value, dict) or "dice" not in value:
                        continue
                    if "-" in str(key):
                        parts = str(key).split("-")
                        start, end = int(parts[0]), int(parts[1])
                    else:
                        start = end = int(key)
                    mode_ranges[mode].append((start, end))
                    dice_colors = [DiceColor[d] for d in value.get("dice", []) if d in DiceColor.__members__]
                    bands.append((start, end, dice_colors))
                compiled[(mode, "ALL")] = bands
                compiled[(mode, "INFANTRY")] = bands
                compiled[(mode, "VEHICLE")] = bands
            else:
                for target_type, table in targets.items():
                    if not isinstance(table, dict):
                        continue
                    bands = []
                    for key, value in table.items():
                        if "-" in str(key):
                            parts = str(key).split("-")
                            start, end = int(parts[0]), int(parts[1])
                        else:
                            start = end = int(key)
                        mode_ranges[mode].append((start, end))
                        dice_colors = [DiceColor[d] for d in value.get("dice", []) if d in DiceColor.__members__] if isinstance(value, dict) else []
                        bands.append((start, end, dice_colors))
                    compiled[(mode, target_type)] = bands

                # Auto-infer missing target categories for area/indirect fire
                if mode == "INDIRECT_FIRE":
                    if (mode, "ALL") in compiled:
                        if (mode, "INFANTRY") not in compiled:
                            compiled[(mode, "INFANTRY")] = compiled[(mode, "ALL")]
                        if (mode, "VEHICLE") not in compiled:
                            compiled[(mode, "VEHICLE")] = compiled[(mode, "ALL")]
                    elif (mode, "INFANTRY") in compiled and (mode, "VEHICLE") not in compiled:
                        compiled[(mode, "VEHICLE")] = compiled[(mode, "INFANTRY")]
                    elif (mode, "VEHICLE") in compiled and (mode, "INFANTRY") not in compiled:
                        compiled[(mode, "INFANTRY")] = compiled[(mode, "VEHICLE")]

        self._compiled_attacks = compiled
        self._mode_ranges = mode_ranges

        # Compile indirect fire properties (Rule 7.1 & card text)
        self.indirect_fire_profile = None
        if "INDIRECT_FIRE" in (self._attack_raw or {}):
            ind = self._attack_raw["INDIRECT_FIRE"]
            defense_loss = "NONE"
            reroll = False
            if isinstance(ind, dict):
                defense_loss = ind.get("defense_loss", "NONE")
                reroll = bool(ind.get("reroll", False) or ind.get("reroll_attack_die", False))

            traits_u = {str(t).upper() for t in (self.traits or [])}
            if "REMOVE_WEAKEST_TERRAIN_DEFENSE" in traits_u and defense_loss == "NONE":
                defense_loss = "WEAKEST_TERRAIN"
            elif "REMOVE_STRONGEST_TERRAIN_DEFENSE" in traits_u and defense_loss == "NONE":
                defense_loss = "STRONGEST_TERRAIN"
            if "ATTACK_DIE_REROLL" in traits_u:
                reroll = True

            self.indirect_fire_profile = {
                "defense_loss": defense_loss,
                "reroll": reroll,
            }

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
            bands = self._compiled_attacks.get((mode, cat_val)) or self._compiled_attacks.get((mode, "ALL"), [])
            for start, end, _ in bands:
                if start <= distance <= end:
                    return True
        return False

    def __deepcopy__(self, memo):
        # UnitType is an immutable static catalog template; share across CoW clones.
        return self


    # =================================================
    # ✅ CORE FUNCTION (Zero string parsing)
    # =================================================
    def get_attack_dice(
        self,
        distance: int,
        target_category: UnitCategory,
        mode: Optional[str] = None,
    ) -> List[DiceColor]:
        """
        Return attack dice given distance and target type.
        Supports multiple attack modes (DIRECT / INDIRECT).
        """
        try:
            if not mode:
                mode = self._resolve_attack_mode(distance)
            if not mode:
                return []

            _trace("ATTACK_MODE", unit=self.code, mode=mode, dist=distance)

            cat_val = target_category.value if hasattr(target_category, "value") else str(target_category)
            bands = self._compiled_attacks.get((mode, cat_val)) or self._compiled_attacks.get((mode, "ALL"), [])
            for start, end, dice in bands:
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
            dice = self._base_defense_raw.get(sector.name)
            if dice is None and sector == AttackSector.ABOVE:
                dice = (
                    self._base_defense_raw.get("ABOVE")
                    or self._base_defense_raw.get("TOP")
                    or self._base_defense_raw.get("FLANK_LEFT")
                    or self._base_defense_raw.get("FLANK")
                    or self._base_defense_raw.get("FRONT")
                )
            elif dice is None and sector in (AttackSector.FLANK_LEFT, AttackSector.FLANK_RIGHT):
                dice = (
                    self._base_defense_raw.get("FLANK")
                    or self._base_defense_raw.get("FRONT")
                )
            if dice is None:
                dice = self._base_defense_raw.get("FRONT", [])
            return [DiceColor[d] for d in dice]
        except Exception:
            return []

    # =================================================
    # SMOKE ACTION (Rule 7.2)
    # =================================================
    def get_smoke_dice(self) -> List[DiceColor]:
        """
        Return smoke dice pool for firing smoke into a target hex
        and nominated adjacent hexes.
        """
        if not self.smoke_profile:
            return []
        return list(self.smoke_profile.get("dice", []))

    def can_fire_smoke(self) -> bool:
        """Check if unit has smoke capability."""
        return self.smoke_profile is not None

