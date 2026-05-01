from assault.core.actions.assault_action import AssaultAction
from assault.core.combat.assault import AssaultResolver


class AssaultExecutor:
    """
    Executes Close Combat (ASSAULT).

    DESIGN (aligned with RangedFireExecutor):
    - Executor does NOT read unit cards
    - Executor does NOT build attack pools
    - Executor delegates ALL logic to the resolver
    - Close combat is always distance = 0
    """

    def __init__(self, resolver: AssaultResolver):
        self.resolver = resolver

    def execute(self, attacker, defender, action: AssaultAction):
        # --- basic sanity ---
        if attacker is None or defender is None:
            return None

        if not attacker.is_alive() or not defender.is_alive():
            return None

        # Close combat is ALWAYS distance 0
        distance = 0

        # Delegate everything to resolver (as RangedFireExecutor does)
        combat_info = self.resolver.resolve(
            attacker=attacker,
            defender=defender,
            distance=distance,
        )

        return combat_info