from assault.core.game_state import GameState
from assault.core.unit import Unit, UnitStatus
from assault.core.visibility import VisibilityService
from assault.core.actions.combat_executor import CombatExecutor
from assault.core.actions.ranged_fire_action import RangedFireAction
from assault.core.combat.ranged_fire import RangedFireResolver


class RangedFireExecutor(CombatExecutor):
    """
    Executes a ranged fire action.

    Responsibilities:
    - Validate visibility
    - Validate that attacker has attack dice available for this range
    - Invoke the RangedFireResolver (dice rolls + raw results)
    - Apply real effects to the game state (damage, suppression)
    - Enrich the combat report with applied effects

    NOTE:
    This class DOES NOT decide randomness.
    It only applies outcomes.
    """

    def __init__(self, state: GameState, resolver: RangedFireResolver):
        self.state = state
        self.resolver = resolver
        self.visibility = VisibilityService()

    # --------------------------------------------------
    # Validation
    # --------------------------------------------------

    def can_execute(
        self,
        *,
        attacker: Unit,
        defender: Unit,
        action: RangedFireAction,
    ) -> bool:
        # 1) Check visibility (rules requirement)
        if not self.visibility.can_see(attacker, defender, self.state):
            return False

        # 2) Compute distance (Chebyshev, as used everywhere else)
        ax, ay = attacker.position
        dx, dy = defender.position
        distance = max(abs(ax - dx), abs(ay - dy))

        # 3) Look up attack dice for this range and defender category
        atk_profile = self.resolver.unit_catalog[attacker.unit_key]
        def_profile = self.resolver.unit_catalog[defender.unit_key]

        defender_category = def_profile.get("category")
        raw_attack_table = atk_profile.get("attack", {})

        attack_table = raw_attack_table.get(
            defender_category,
            next(iter(raw_attack_table.values()), {})
        )

        # Use the SAME range logic as the resolver
        dice = self.resolver._dice_for_distance(attack_table, distance)

        # 4) Executable only if there is actual firepower
        return len(dice) > 0

    # --------------------------------------------------
    # Execution
    # --------------------------------------------------

    def execute(
        self,
        *,
        attacker: Unit,
        defender: Unit,
        action: RangedFireAction,
    ):
        # --------------------------------------------------
        # Spatial context
        # --------------------------------------------------
        ax, ay = attacker.position
        dx, dy = defender.position
        distance = max(abs(ax - dx), abs(ay - dy))
        flank = self._determine_flank(attacker, defender)

        # --------------------------------------------------
        # Snapshot defender state BEFORE combat
        # --------------------------------------------------
        strength_before = defender.strength
        alive_before = defender.is_alive()

        # --------------------------------------------------
        # Resolve combat (dice are rolled here)
        # --------------------------------------------------
        report = action.resolve(
            resolver=self.resolver,
            attacker=attacker,
            defender=defender,
            distance=distance,
            flank=flank,
        )

        # --------------------------------------------------
        # Apply real effects to game state
        # --------------------------------------------------
        if report.hits:
            defender.apply_damage(report.hits)

        if report.suppressions and defender.is_alive():
            defender.statuses.add(UnitStatus.SUPPRESSED)

        # --------------------------------------------------
        # Snapshot defender state AFTER combat
        # --------------------------------------------------
        strength_after = defender.strength
        alive_after = defender.is_alive()

        # --------------------------------------------------
        # Enrich report with applied effects
        # --------------------------------------------------
        report.effects = {
            "strength_before": strength_before,
            "strength_after": strength_after,
            "damage_applied": max(0, strength_before - strength_after),
            "alive_before": alive_before,
            "alive_after": alive_after,
            "suppressed": UnitStatus.SUPPRESSED in defender.statuses,
        }

        return report