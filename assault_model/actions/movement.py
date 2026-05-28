from assault_model.actions.base import MovementAction
from assault_model.actions.action_type import ActionType
from assault_model.map.hex_coord import HexCoord


class MoveAction(MovementAction):
    """
    Movement intent action.
    """

    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.MOVE)
        self.path = path

        # ✅ 💣 ID de acción
        if self.path:
            dest = self.path[-1]
            self.action_id = f"MOVE:{unit_id}:{dest.q}:{dest.r}"
        else:
            self.action_id = f"MOVE:{unit_id}:NONE"

    @property
    def destination(self) -> HexCoord | None:
        return self.path[-1] if self.path else None


class AdvanceAction(MovementAction):
    """
    Advance movement intent action.
    """

    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.ADVANCE)
        self.path = path

        # ✅ 💣 ID de acción
        if self.path:
            dest = self.path[-1]
            self.action_id = f"ADVANCE:{unit_id}:{dest.q}:{dest.r}"
        else:
            self.action_id = f"ADVANCE:{unit_id}:NONE"

    @property
    def destination(self) -> HexCoord | None:
        return self.path[-1] if self.path else None


class FastMoveAction(MovementAction):
    """
    Fast movement intent action.
    """

    def __init__(self, unit_id: str, path: list[HexCoord]):
        super().__init__(unit_id, ActionType.FAST_MOVE)
        self.path = path

        # ✅ 💣 ID de acción
        if self.path:
            dest = self.path[-1]
            self.action_id = f"FAST_MOVE:{unit_id}:{dest.q}:{dest.r}"
        else:
            self.action_id = f"FAST_MOVE:{unit_id}:NONE"

    @property
    def destination(self) -> HexCoord | None:
        return self.path[-1] if self.path else None
