from assault.core.actions.assault_action import AssaultAction
from assault.core.combat.assault import AssaultResolver


class AssaultExecutor:
    """
    Executes Close Combat (ASSAULT).

    Correct architecture:
    - Executor does NOT compute distance
    - Executor does NOT pass distance
    - Executor delegates everything to resolver
    - Resolver assumes close combat = distance 0 internally
    """

    def __init__(self, resolver: AssaultResolver):
        self.resolver = resolver

    def execute(self, attacker, defender, action: AssaultAction):
        # --- sanity checks ---
        if attacker is None or defender is None:
            return None

        if not attacker.is_alive() or not defender.is_alive():
            return None

        # ✅ No distance here
        return self.resolver.resolve(
            attacker=attacker,
            defender=defender,
        )