from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.attack_sector import AttackSector
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class CloseCombatContext:
    """
    Context specific to close combat (ASSAULT).

    This context is round-based and mutable.
    It must NOT be used for ranged or reaction combat.
    """

    def __init__(
        self,
        attacker,
        defender,
        combat_mode: CombatMode,
        attack_sector: AttackSector,
    ):
        # Units involved
        self.attacker = attacker
        self.defender = defender

        # Combat metadata
        self.combat_mode = combat_mode
        self.attack_sector = attack_sector

        # Round-related state (11.1 / 11.1.5)
        self.round_number: int = 1
        self.first_round: bool = True
        self.adrenaline_rush: bool = True  # ignore first suppression in round 1

        _trace(
            "CC_CONTEXT_INIT",
            attacker_id=getattr(attacker, "unit_id", None),
            attacker_code=getattr(getattr(attacker, "unit_type", None), "code", None),
            defender_id=getattr(defender, "unit_id", None),
            defender_code=getattr(getattr(defender, "unit_type", None), "code", None),
            sector=attack_sector.name if attack_sector else None,
        )