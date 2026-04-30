# assault_model/combat/reaction_fire_resolution.py
from assault_model.combat.combat_resolution import CombatResolutionResult, resolve_combat
from assault_model.combat.reaction_state import ReactionState
from assault_model.combat.line_of_sight import LineOfSight


def resolve_reaction_fire(
    reaction_state: ReactionState,
    los: LineOfSight,
    attack_profile,
    defense_profile,
    band,
):
    if not reaction_state.available:
        return None

    reaction_state.consume()
    return resolve_combat(
        attack_profile=attack_profile,
        defense_profile=defense_profile,
        band=band,
    )