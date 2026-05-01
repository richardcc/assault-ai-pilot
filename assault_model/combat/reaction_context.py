# assault_model/combat/reaction_context.py
#
# Reaction context container.
#
# RESPONSIBILITY:
# - Hold reaction data
# - Store RAW close combat result for the runtime
#
# IMPORTANT:
# - NO logic
# - NO EventBus emission

from dataclasses import dataclass
from assault_model.combat.reaction_trigger import ReactionTrigger
from assault_model.units.unit_instance import UnitInstance


@dataclass
class ReactionContext:
    trigger: ReactionTrigger
    reactor: UnitInstance
    moving_unit: UnitInstance
    entered_hex: tuple[int, int]

    # RAW close combat result (set by runtime when reaction is resolved)
    combat_result = None