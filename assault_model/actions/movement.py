from assault_model.actions.base import MovementAction
from assault_model.actions.action_type import ActionType
from assault_model.map.hex_coord import HexCoord


class MoveAction(MovementAction):
    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.MOVE)
        self.path = path


class AdvanceAction(MovementAction):
    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.ADVANCE)
        self.path = path


class FastMoveAction(MovementAction):
    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.FAST_MOVE)
        self.path = path
