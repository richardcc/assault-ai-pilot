# assault_sim/heuristics/tactical_path_heuristic.py

from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.map.hex_coord import HexCoord

from assault_sim.heuristics.pathfinding import bfs_hex_path


class TacticalPathHeuristic:
    """
    TacticalPathHeuristic (VP-seeking)

    Behaviour:
    - Compute a real hex-path to the Victory Point
    - Move ONE hex per activation (tactical scale)
    - Let the motor handle reactions and combat
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def choose_action(self, state):
        unit = state.active_unit

        # ✔️ No active unit
        if unit is None:
            return None

        # ✔️ Dead unit explicitly waits
        if not unit.alive:
            return WaitAction(unit.unit_id)

        # ✔️ No Victory Conditions
        if not state.victory or not state.victory.points:
            return WaitAction(unit.unit_id)

        start = unit.position

        # Use first VP (you can extend later)
        goal = state.victory.points[0].hex_coords

        path = bfs_hex_path(start, goal, state)

        if path and len(path) > 0:
            next_hex = path[0]
            return MoveAction(
                unit.unit_id,
                [HexCoord(*next_hex)],
            )

        # No path available
        return WaitAction(unit.unit_id)