# assault_model/core/vp_tracker.py

from assault_model.map.hex_ownership import HexOwnership
from assault_model.core.victory_conditions import VictoryConditions


class VictoryPointTracker:
    """
    Tracks victory points per side across turns.
    """

    def __init__(self, conditions: VictoryConditions):
        self.conditions = conditions
        self.score = {
            HexOwnership.SIDE_A: 0,
            HexOwnership.SIDE_B: 0,
        }

    def apply_turn(self, hex_states: dict[tuple[int, int], HexOwnership]) -> None:
        """
        Apply victory point rules for one turn.
        """
        for vp in self.conditions.points:
            owner = hex_states.get(vp.hex_coords, HexOwnership.NONE)
            if owner in self.score:
                self.score[owner] += vp.per_turn

    # ✅ API PÚBLICA: TOTAL DE PUNTOS
    @property
    def total_points(self) -> int:
        """
        Total victory points accumulated by all sides.
        Useful for RL reward, debug and analytics.
        """
        return sum(self.score.values())

    # ✅ (opcional pero útil) puntos por bando
    def points_by_side(self) -> dict:
        """
        Return a copy of the VP score per side.
        """
        return dict(self.score)
