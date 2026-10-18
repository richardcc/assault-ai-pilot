from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.attack_sector import AttackSector
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class CombatResolutionContext:
    """
    Context for resolving CLOSE COMBAT (ASSAULT).

    This context is:
    - round-based
    - mutable
    - owned by the close combat resolver

    IMPORTANT:
    - This context is ONLY valid for ASSAULT resolution.
    - It must NOT be reused for ranged or reaction combat.
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
        # CC-001: attacker crossed obstacle edge into defender hex.
        self.crossed_obstacle: bool = False

        # Multi-unit combined assault support sub-phases (Palma et al. 2025, Sec. 3.3):
        # Adjacent units committing coordinated flanking/covering support prior to close melee
        self.supporting_attackers: list = []
        self.supporting_defenders: list = []

        _trace(
            "CC_CONTEXT_INIT",
            attacker_id=getattr(attacker, "unit_id", None),
            attacker_code=getattr(getattr(attacker, "unit_type", None), "code", None),
            defender_id=getattr(defender, "unit_id", None),
            defender_code=getattr(getattr(defender, "unit_type", None), "code", None),
            sector=attack_sector.name if attack_sector else None,
            crossed_obstacle=self.crossed_obstacle,
        )

    def commit_support_unit(self, unit, side: str = "attacker", support_type: str = "combined_assault"):
        """
        Commits an adjacent squad into the coordinated assault sequence (Palma et al. 2025, Sec. 3.3, Fig. 3).
        In round 1, contributing squads contribute coordinated suppression/flanking pressure.
        """
        if side == "attacker":
            if unit not in self.supporting_attackers:
                self.supporting_attackers.append(unit)
                _trace("CC_SUPPORT_COMMITTED", side="attacker", unit_id=getattr(unit, "unit_id", None), support_type=support_type)
        else:
            if unit not in self.supporting_defenders:
                self.supporting_defenders.append(unit)
                _trace("CC_SUPPORT_COMMITTED", side="defender", unit_id=getattr(unit, "unit_id", None), support_type=support_type)

