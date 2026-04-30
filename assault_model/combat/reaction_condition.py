from assault_model.combat.reaction_trigger import ReactionTrigger


class ReactionCondition:
    """
    Declarative definition of when a reaction is allowed.
    Evaluation is performed by runtime / policy.
    """

    def __init__(
        self,
        trigger: ReactionTrigger,
        los_required: bool = True,
    ):
        self.trigger = trigger
        self.los_required = los_required