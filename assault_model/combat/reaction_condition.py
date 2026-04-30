# assault_model/combat/reaction_condition.py
from assault_model.combat.reaction_trigger import ReactionTrigger
from assault_model.combat.line_of_sight import LineOfSight


class ReactionCondition:
    def __init__(
        self,
        trigger: ReactionTrigger,
        los_required: bool = True,
    ):
        self.trigger = trigger
        self.los_required = los_required

    def is_met(self, los: LineOfSight) -> bool:
        if self.los_required and los != LineOfSight.CLEAR:
            return False
        return True