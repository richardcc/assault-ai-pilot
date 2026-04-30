from dataclasses import dataclass
import random

from assault.core.unit import Unit
from assault.core.combat.flank import Flank

# ✅ GLOBAL dice (single source of truth)
from assault.core.combat.dice import DiceColor, CombatSymbol, roll_die


# --------------------------------------------------
# Combat report
# --------------------------------------------------

@dataclass
class RangedFireReport:
    hits: int
    suppressions: int
    rolls: dict


# --------------------------------------------------
# Ranged fire resolver
# --------------------------------------------------

class RangedFireResolver:
    """
    Ranged fire resolver.

    - Uses GLOBAL dice (dice.py)
    - Selects attack table by defender category
    - Rolls dice and computes results
    - DOES NOT apply damage
    """

    def __init__(self, unit_catalog: dict, rng: random.Random | None = None) -> None:
        self.unit_catalog = unit_catalog
        self.rng = rng or random.Random()

    # --------------------------------------------------

    def resolve(
        self,
        *,
        attacker: Unit,
        defender: Unit,
        distance: int,
        flank: Flank,
    ) -> RangedFireReport:

        atk_profile = self.unit_catalog[attacker.unit_key]
        def_profile = self.unit_catalog[defender.unit_key]

        # --------------------------------------------------
        # ✅ Select attack table by defender category
        # --------------------------------------------------

        defender_category = def_profile.get("category")
        raw_attack_table = atk_profile["attack"]

        if defender_category in raw_attack_table:
            attack_table = raw_attack_table[defender_category]
        else:
            attack_table = next(iter(raw_attack_table.values()))

        # --------------------------------------------------
        # Dice selection by distance (robust)
        # --------------------------------------------------

        attack_dice = self._dice_for_distance(attack_table, distance)

        # --------------------------------------------------
        # Defense dice (from defender base defense)
        # --------------------------------------------------

        defense_table = def_profile.get("base_defense", {})
        defense_dice = defense_table.get(flank.name, [])

        hits = 0
        suppressions = 0

        attack_rolls = []
        defense_rolls = []

        # --------------------------------------------------
        # Roll attack dice
        # --------------------------------------------------

        for die in attack_dice:
            symbol = roll_die(DiceColor[die], self.rng)

            attack_rolls.append({
                "die": die,
                "symbol": symbol.name,
            })

            if symbol in (CombatSymbol.HIT, CombatSymbol.CRITICAL):
                hits += 1
            elif symbol == CombatSymbol.SUPPRESSION:
                suppressions += 1

        hits_before_defense = hits

        # --------------------------------------------------
        # Roll defense dice (cancel)
        # --------------------------------------------------

        for die in defense_dice:
            symbol = roll_die(DiceColor[die], self.rng)

            defense_rolls.append({
                "die": die,
                "symbol": symbol.name,
            })

            if symbol == CombatSymbol.CANCEL:
                hits = max(0, hits - 1)

        # --------------------------------------------------
        # Return report
        # --------------------------------------------------

        return RangedFireReport(
            hits=hits,
            suppressions=suppressions,
            rolls={
                "attack_dice": attack_rolls,
                "defense_dice": defense_rolls,
                "hits_before_defense": hits_before_defense,
                "hits_after_defense": hits,
                "distance": distance,
                "flank": flank.name,
                "defender_category": defender_category,
            },
        )

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _dice_for_distance(self, table: dict, distance: int) -> list:
        """
        Select dice entry matching the given distance.
        Falls back to nearest lower range if needed.
        """
        fallback = []

        for key, entry in table.items():
            if "-" in key:
                lo, hi = map(int, key.split("-"))
                if lo <= distance <= hi:
                    return entry["dice"]
                if hi < distance:
                    fallback = entry["dice"]
            else:
                d = int(key)
                if d == distance:
                    return entry["dice"]
                if d < distance:
                    fallback = entry["dice"]

        return fallback