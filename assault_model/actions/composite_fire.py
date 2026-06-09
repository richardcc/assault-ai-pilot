from assault_model.actions.action import Action
from assault_model.actions.action_type import ActionType


class MoveThenFireAction(Action):
    """
    Composite action:
    - Move (up to half movement allowance, rounded up)
    - Then execute ranged fire
    """

    def __init__(self, unit_id: str, move_path: list, fire_action):
        super().__init__(unit_id, ActionType.MOVE)
        self.move_path = move_path or []
        self.fire_action = fire_action
        self.target_id = getattr(fire_action, "target_id", getattr(fire_action, "target_hex", None))
        self.target = getattr(fire_action, "target", None)
        self.attack_mode = getattr(fire_action, "attack_mode", None)
        # Mark this attack as a move/fire attack for ranged modifiers.
        if self.fire_action is not None:
            self.fire_action.move_fire_defense_bonus = True
        if self.move_path:
            end = self.move_path[-1]
            self.action_id = (
                f"MOVE_FIRE:{unit_id}:{end.q}:{end.r}:"
                f"{getattr(self.fire_action, 'action_id', 'NO_FIRE')}"
            )
        else:
            self.action_id = f"MOVE_FIRE:{unit_id}:NONE:{getattr(self.fire_action, 'action_id', 'NO_FIRE')}"


class FireThenMoveAction(Action):
    """
    Composite action:
    - Execute ranged fire
    - Then move (up to half movement allowance, rounded up)
    """

    def __init__(self, unit_id: str, fire_action, move_path: list):
        super().__init__(unit_id, ActionType.MOVE)
        self.fire_action = fire_action
        self.move_path = move_path or []
        self.target_id = getattr(fire_action, "target_id", getattr(fire_action, "target_hex", None))
        self.target = getattr(fire_action, "target", None)
        self.attack_mode = getattr(fire_action, "attack_mode", None)
        # Mark this attack as a move/fire attack for ranged modifiers.
        if self.fire_action is not None:
            self.fire_action.move_fire_defense_bonus = True
        if self.move_path:
            end = self.move_path[-1]
            self.action_id = (
                f"FIRE_MOVE:{unit_id}:{getattr(self.fire_action, 'action_id', 'NO_FIRE')}:"
                f"{end.q}:{end.r}"
            )
        else:
            self.action_id = f"FIRE_MOVE:{unit_id}:{getattr(self.fire_action, 'action_id', 'NO_MOVE')}:NONE"

