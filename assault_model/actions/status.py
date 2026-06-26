# assault_model/actions/status.py
from assault_model.actions.action import Action
from assault_model.actions.action_type import ActionType


class WaitAction(Action):
    def __init__(self, unit_id: str):
        super().__init__(unit_id, ActionType.WAIT)
        self.action_id = f"WAIT:{unit_id}"


class EndTurnAction(Action):
    def __init__(self, unit_id: str):
        super().__init__(unit_id, ActionType.END_TURN)
        self.action_id = f"END_TURN:{unit_id}"