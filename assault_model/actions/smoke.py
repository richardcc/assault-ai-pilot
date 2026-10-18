from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class FireSmokeAction(CombatAction):
    """
    Declares an indirect smoke fire action (Rule 7.2 Firing Smoke).

    Design:
    - Target hex is the primary hex (q, r).
    - Up to two nominated adjacent hexes (adjacent to target hex) can be targeted
      by dice that failed to generate smoke in earlier stages.
    - All targeted hexes must be in LOS (firer or friendly spotter).
    - Firing smoke does NOT cause damage or suppression to units in hexes.
    - Units inside target hexes receive NO defense roll.
    """

    def __init__(
        self,
        unit_id: str,
        target_hex: tuple[int, int],
        adjacent_hexes: list[tuple[int, int]] | None = None,
    ):
        super().__init__(unit_id, ActionType.FIRE_SMOKE)
        self.target_hex = (int(target_hex[0]), int(target_hex[1]))
        raw_adj = adjacent_hexes or []
        self.adjacent_hexes = [(int(h[0]), int(h[1])) for h in raw_adj][:2]
        self.combat_mode = CombatMode.SMOKE

        q, r = self.target_hex
        self.action_id = f"FIRE_SMOKE:{unit_id}:{q}:{r}"

    def __repr__(self) -> str:
        return (
            f"FireSmokeAction("
            f"unit_id={self.unit_id}, "
            f"target_hex={self.target_hex}, "
            f"adjacent_hexes={self.adjacent_hexes}"
            f")"
        )
