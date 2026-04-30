from dataclasses import dataclass
from assault_model.combat.reaction_trigger import ReactionTrigger
from assault_model.units.unit_instance import UnitInstance


@dataclass(frozen=True)
class ReactionContext:
    """
    Runtime reaction window.
    The game is paused until the reacting player chooses an action.
    """

    trigger: ReactionTrigger
    reactor: UnitInstance
    moving_unit: UnitInstance
    entered_hex: tuple[int, int]