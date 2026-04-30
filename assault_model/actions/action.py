from typing import Any
from assault_model.actions.action_type import ActionType


class Action:
    def __init__(
        self,
        unit_id: str,
        action_type: ActionType,
        payload: Any | None = None,
    ):
        self.unit_id = unit_id
        self.action_type = action_type
        self.payload = payload