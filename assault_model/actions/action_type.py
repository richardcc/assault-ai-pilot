from enum import Enum
from assault_model.actions.action_category import ActionCategory


class ActionType(Enum):
    # Movement
    MOVE = (ActionCategory.MOVEMENT, "MOVE")
    ADVANCE = (ActionCategory.MOVEMENT, "ADVANCE")
    FAST_MOVE = (ActionCategory.MOVEMENT, "FAST_MOVE")

    # Combat
    RANGED_ATTACK = (ActionCategory.COMBAT, "RANGED_ATTACK")
    CLOSE_COMBAT = (ActionCategory.COMBAT, "CLOSE_COMBAT")

    # Control / status
    WAIT = (ActionCategory.STATUS, "WAIT")
    END_TURN = (ActionCategory.STATUS, "END_TURN")

    def __init__(self, category: ActionCategory, label: str):
        self.category = category
        self.label = label
