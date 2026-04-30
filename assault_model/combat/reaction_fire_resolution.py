from assault_model.combat.combat_resolution import (
    CombatResolutionResult,
    resolve_combat,
)
from assault_model.combat.reaction_state import ReactionState
from assault_model.combat.line_of_sight import LineOfSight


def resolve_reaction_fire(
    reactor,
    target,
    game_map,
    attack_profile,
    defense_profile,
    band,
):
    """
    Resolve Reaction Fire as a standard ranged fire action,
    respecting reaction availability and LOS.

    Returns CombatResolutionResult or None if reaction is not allowed.
    """

    # Ensure reactor has reaction state
    if not hasattr(reactor, "reaction_state"):
        reactor.reaction_state = ReactionState()

    reaction_state: ReactionState = reactor.reaction_state

    # Check availability
    if not reaction_state.available:
        return None

    # LOS check
    los = game_map.get_los(reactor.position, target.position) \
        if hasattr(game_map, "get_los") else LineOfSight.CLEAR

    if los == LineOfSight.BLOCKED:
        return None

    # Consume reaction usage
    reaction_state.consume()

    # ✅ Reaction fire consumes activation by default
    # (Runtime should ALSO mark unit as activated)
    reactor.activated = True

    # Delegate actual combat to core resolver
    result: CombatResolutionResult = resolve_combat(
        attacker_profile=attack_profile,
        defender_profile=defense_profile,
        band=band,
        los=los,
    )

    return result