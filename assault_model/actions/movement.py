from assault_model.actions.base import MovementAction
from assault_model.actions.action_type import ActionType
from assault_model.map.hex_coord import HexCoord


class MoveAction(MovementAction):
    """
    Movement intent action.

    The path represents the movement target(s), NOT the origin.
    The origin must always be obtained from the current GameState.
    """

    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.MOVE)
        self.path = path

    @property
    def destination(self) -> HexCoord | None:
        return self.path[-1] if self.path else None


class AdvanceAction(MovementAction):
    """
    Advance movement intent action.

    The path represents the movement target(s), NOT the origin.
    """

    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.ADVANCE)
        self.path = path

    @property
    def destination(self) -> HexCoord | None:
        return self.path[-1] if self.path else None


class FastMoveAction(MovementAction):
    """
    Fast movement intent action.

    The path represents the movement target(s), NOT the origin.
    """

    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.FAST_MOVE)
        self.path = path

    @property
    def destination(self) -> HexCoord | None:
        return self.path[-1] if self.path else None