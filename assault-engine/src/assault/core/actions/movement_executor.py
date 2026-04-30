from assault.core.game_state import GameState
from assault.core.unit import Unit
from assault.core.actions.movement_action import MovementAction


class MovementExecutor:
    """
    Applies movement actions to the GameState.
    """

    def __init__(self, state: GameState) -> None:
        self.state = state

    def can_execute(
        self,
        *,
        unit: Unit,
        action: MovementAction,
    ) -> bool:
        q, r = action.target_hex

        # Hex must exist
        if (q, r) not in self.state.hexes:
            return False

        # Destination must be free
        if self.state.hexes[(q, r)].occupant is not None:
            return False

        return True

    def execute(
        self,
        *,
        unit: Unit,
        action: MovementAction,
    ) -> None:
        if not self.can_execute(unit=unit, action=action):
            raise ValueError("Invalid movement")

        # Clear old hex
        oq, or_ = unit.position
        self.state.hexes[(oq, or_)].occupant = None

        # Move unit
        unit.position = action.target_hex
        self.state.hexes[action.target_hex].occupant = unit.unit_id