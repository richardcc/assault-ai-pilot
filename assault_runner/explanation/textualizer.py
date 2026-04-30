"""
Textualizer – Tactical Explanation Generator

Domain-aware, side-agnostic explanations based on state transitions.

Properties:
- No hardcoded factions
- No logging
- No PPO dependence
- Pure post-hoc explanation
"""

from typing import Optional
from assault.core.game_state import GameState


def explain_action(
    *,
    prev_state: GameState,
    next_state: GameState,
    unit_id: str,
    action: str,
    report: Optional[object] = None,
    lang: str = "en",
) -> Optional[str]:

    unit_before = prev_state.get_unit(unit_id)
    unit_after = next_state.get_unit(unit_id)

    if unit_before is None or unit_after is None:
        return None

    explanations = []

    # ==================================================
    # MOVEMENT
    # ==================================================

    if action.startswith("MOVE_"):
        x0, y0 = unit_before.position
        x1, y1 = unit_after.position

        dx = x1 - x0
        dy = y1 - y0

        direction = _direction_from_delta(dx, dy)
        explanations.append(
            f"The unit moved {direction} to improve its position."
        )

        d0 = _nearest_enemy_distance(prev_state, unit_id)
        d1 = _nearest_enemy_distance(next_state, unit_id)

        if d0 is not None and d1 is not None:
            if d1 < d0:
                explanations.append(
                    "The move reduced distance to the nearest enemy."
                )
            elif d1 > d0:
                explanations.append(
                    "The move increased distance from nearby threats."
                )

    # ==================================================
    # RANGED COMBAT
    # ==================================================

    elif action == "RANGED_FIRE":
        explanations.append(
            "The unit fired at an enemy unit."
        )

        if report is not None:
            hits = report.effects.get("damage_applied", 0)
            killed = report.effects.get("alive_after") is False

            if hits > 0:
                explanations.append(
                    f"The attack inflicted {hits} point(s) of damage."
                )

            if killed:
                explanations.append(
                    "The enemy unit was eliminated."
                )

    # ==================================================
    # ASSAULT
    # ==================================================

    elif action == "ASSAULT":
        explanations.append(
            "The unit assaulted an adjacent enemy position."
        )

    # ==================================================
    # VICTORY POINT CONTEXT
    # ==================================================

    side = unit_after.side
    had_vp_before = prev_state.controls_any_vp(side)
    has_vp_after = next_state.controls_any_vp(side)

    if not had_vp_before and has_vp_after:
        explanations.append(
            "The unit’s side gained control of an objective."
        )
    elif had_vp_before and has_vp_after:
        explanations.append(
            "The action helped maintain control of an objective."
        )
    elif had_vp_before and not has_vp_after:
        explanations.append(
            "The action resulted in the loss of control over an objective."
        )

    if not explanations:
        return None

    return " ".join(explanations)


# --------------------------------------------------
# Helpers (internal)
# --------------------------------------------------

def _direction_from_delta(dx: int, dy: int) -> str:
    if dx > 0:
        return "east"
    if dx < 0:
        return "west"
    if dy > 0:
        return "north"
    if dy < 0:
        return "south"
    return "to a nearby position"


def _nearest_enemy_distance(state: GameState, unit_id: str) -> Optional[int]:
    unit = state.get_unit(unit_id)
    if unit is None:
        return None

    x0, y0 = unit.position
    distances = []

    for side, units in state.units.items():
        if side == unit.side:
            continue
        for enemy in units.values():
            if enemy.is_alive():
                x1, y1 = enemy.position
                distances.append(abs(x1 - x0) + abs(y1 - y0))

    return min(distances) if distances else None