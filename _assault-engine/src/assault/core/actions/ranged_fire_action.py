from dataclasses import dataclass

from assault.core.combat.ranged_fire import RangedFireResolver, RangedFireReport
from assault.core.combat.flank import Flank


@dataclass(frozen=True)
class RangedFireAction:
    """
    Declarative ranged fire action.

    This action:
    - Does NOT validate range
    - Does NOT validate LOS
    - Does NOT raise errors
    - Only delegates combat resolution to the resolver

    All validation is handled by the Executor.
    """

    def resolve(
        self,
        *,
        resolver: RangedFireResolver,
        attacker,
        defender,
        distance: int,
        flank: Flank,
    ) -> RangedFireReport:
        return resolver.resolve(
            attacker=attacker,
            defender=defender,
            distance=distance,
            flank=flank,
        )