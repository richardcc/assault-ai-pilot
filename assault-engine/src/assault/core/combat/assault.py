from dataclasses import dataclass
import random

from assault.core.unit import Unit
from assault.core.combat.dice import DiceColor, CombatSymbol, roll_die


# --------------------------------------------------
# Combat report
# --------------------------------------------------

@dataclass
class AssaultReport:
    hits: int
    rolls: dict
    effects: dict | None = None


# --------------------------------------------------
# Assault resolver
# --------------------------------------------------

class AssaultResolver:
    """
    Close Combat (ASSAULT) resolver.

    RULEBOOK-CORRECT (INFANTRY vs INFANTRY):
    - Both units are in the SAME hex
    - NO distance evaluation (always implicit 0)
    - NO flank (omnidirectional combat)
    - Attack dice come from attack["INFANTRY"]["0"]
    - Defense uses base defense only
    - Defense cancels hits on BLANK (engine convention)
    """

    def __init__(self, unit_catalog: dict, rng: random.Random | None = None) -> None:
        self.unit_catalog = unit_catalog
        self.rng = rng or random.Random()

    def resolve(
        self,
        *,
        attacker: Unit,
        defender: Unit,
    ) -> AssaultReport | None:

        # ------------------------------
        # Sanity checks
        # ------------------------------
        if attacker is None or defender is None:
            return None

        if not attacker.is_alive() or not defender.is_alive():
            return None

        atk_profile = self.unit_catalog[attacker.unit_key]
        def_profile = self.unit_catalog[defender.unit_key]

        # ------------------------------
        # Close combat attack dice
        # INFANTRY at range 0
        # ------------------------------
        attack_table = atk_profile["attack"].get(def_profile["category"], {})
        attack_entry = attack_table.get("0")

        if attack_entry is None:
            return None

        attack_dice = attack_entry.get("dice", [])

        # ------------------------------
        # Defense dice (NO FLANK IN CC)
        # Use base defense as-is
        # ------------------------------
        defense_table = def_profile.get("base_defense", {})
        defense_dice = defense_table.get("FRONT", [])

        hits = 0
        attack_rolls = []
        defense_rolls = []

        # ------------------------------
        # Roll attack dice
        # ------------------------------
        for die in attack_dice:
            symbol = roll_die(DiceColor[die], self.rng)
            attack_rolls.append(symbol)

            if symbol in (CombatSymbol.HIT, CombatSymbol.CRITICAL):
                hits += 1

        # ------------------------------
        # Roll defense dice
        # BLANK cancels one hit (engine convention)
        # ------------------------------
        for die in defense_dice:
            symbol = roll_die(DiceColor[die], self.rng)
            defense_rolls.append(symbol)

            if symbol == CombatSymbol.BLANK:
                hits = max(0, hits - 1)

        return AssaultReport(
            hits=hits,
            rolls={
                "attack_dice": [s.name for s in attack_rolls],
                "defense_dice": [s.name for s in defense_rolls],
            },
        )