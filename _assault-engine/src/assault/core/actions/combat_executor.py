from assault.core.unit import Unit
from assault.core.combat.flank import Flank


class CombatExecutor:
    """
    Base class for all combat executors.
    Provides common combat context helpers.
    """

    def _determine_flank(self, attacker: Unit, defender: Unit) -> Flank:
        ax, ay = attacker.position
        dx, dy = defender.position

        vx = ax - dx
        vy = ay - dy

        facing = getattr(defender, "facing", "N")

        facing_vectors = {
            "N": (0, -1),
            "S": (0, 1),
            "E": (1, 0),
            "W": (-1, 0),
        }

        fx, fy = facing_vectors[facing]
        dot = vx * fx + vy * fy

        if dot > 0:
            return Flank.FRONT
        elif dot < 0:
            return Flank.REAR
        else:
            return Flank.FLANK