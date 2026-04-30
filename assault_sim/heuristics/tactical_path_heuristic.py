# assault_sim/heuristics/tactical_path_heuristic.py

from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.map.hex_coord import HexCoord


class TacticalPathHeuristic:
    """
    TacticalPathHeuristic

    Behaviour:
    - Move one hex at a time towards the Victory Point
    - If moving into an enemy hex, the motor converts it into Assault
    - Reaction Fire is OPTIONAL and handled by the motor
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def choose_action(self, state):
        unit = state.active_unit

        if unit is None or not unit.alive:
            return WaitAction()

        next_step = self._step_towards_objective(unit, state)
        if next_step:
            return MoveAction(
                unit.unit_id,
                [HexCoord(*next_step)],
            )

        return WaitAction()

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------
    def _step_towards_objective(self, unit, state):
        """
        Simple greedy step towards the closest Victory Point.
        No global pathfinding required.
        """
        if not state.victory:
            return None

        uq, ur = unit.position

        for vq, vr in state.victory.get_positions():
            dq = vq - uq
            dr = vr - ur

            # simple axial step (greedy)
            step_q = uq + (1 if dq > 0 else -1 if dq < 0 else 0)
            step_r = ur + (1 if dr > 0 else -1 if dr < 0 else 0)

            # check map bounds
            if state.game_map.get_hex(step_q, step_r):
                return (step_q, step_r)

        return None