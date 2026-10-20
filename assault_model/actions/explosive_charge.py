from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class ExplosiveChargeAction(CombatAction):
    """
    Declares detonation of an explosive charge (Rule 12.5 & Combat Engineers card).

    Design:
    - Initiated by a unit with the EXPLOSIVE_CHARGE trait (typically engineers).
    - Can target an adjacent hex (distance 1) containing:
      * A building (single or multi-story)
      * A fortification (bunker, casemate, pillbox, gun_emplacement, trench, sandbag)
      * An obstacle (barbed_wire, minefield, tank_barricade)
    - Resolved during support / combat phase.
    - Attack die: 1 RED attack die.
    - Defense die: Strongest terrain defense die of target, or 1 GREEN die if none available.
    """

    def __init__(
        self,
        unit_id: str,
        target_hex: tuple[int, int],
        target_feature: str = "structure",
    ):
        super().__init__(unit_id, ActionType.EXPLOSIVE_CHARGE)
        self.target_hex = (int(target_hex[0]), int(target_hex[1]))
        self.target_feature = str(target_feature)
        self.combat_mode = CombatMode.EXPLOSIVE_CHARGE

        q, r = self.target_hex
        self.action_id = f"EXPLOSIVE_CHARGE:{unit_id}:{q}:{r}:{self.target_feature}"

    def __repr__(self) -> str:
        return (
            f"ExplosiveChargeAction("
            f"unit_id={self.unit_id}, "
            f"target_hex={self.target_hex}, "
            f"target_feature={self.target_feature}"
            f")"
        )
