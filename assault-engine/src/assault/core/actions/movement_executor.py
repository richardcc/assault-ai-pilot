# assault/core/actions/movement_executor.py

from assault.core.game_state import GameState
from assault.core.actions.movement_action import MovementAction


class MovementExecutor:
    """
    Applies movement actions to the GameState.
    """

    def __init__(self, state: GameState) -> None:
        self.state = state

    def execute(self, action: MovementAction) -> None:
        if not action.can_execute(self.state):
            raise ValueError("Invalid movement")

        unit = action.unit
        target_q, target_r = action.target_hex

        # Clear old hex
        old_q, old_r = unit.position
        self.state.hexes[(old_q, old_r)].occupant = None

        # Move unit
        unit.position = (target_q, target_r)
        self.state.hexes[(target_q, target_r)].occupant = unit.unit_id