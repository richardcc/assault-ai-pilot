# assault_model/actions/status.py
from assault_model.actions.action import Action
from assault_model.actions.action_type import ActionType


class WaitAction(Action):
    def __init__(self, unit_id: str):
        super().__init__(unit_id, ActionType.WAIT)


class EndTurnAction(Action):
    def __init__(self, unit_id: str):
        super().__init__(unit_id, ActionType.END_TURN)