# assault_model/actions/resolution.py
#
# This module resolves high-level actions into concrete game state changes.
#
# RESPONSIBILITY:
# - Apply an action (movement or combat) to the GameState
# - Return the resulting GameState
# - Return detailed combat results (if any)
#
# IMPORTANT:
# - This module does NOT print anything
# - This module does NOT render anything
# - All visible output MUST go through the EventBus (observability)
#
# DEBUG TRACES:
# - Optional, controlled by ASSAULT_DEBUG_TRACE
# - Never sent to the EventBus

from copy import deepcopy
import os

from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
from assault_model.actions.base import CombatAction
from assault_model.actions.combat_mode import CombatMode

from assault_model.state.game_state import GameState

from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.combat_resolution import CombatResolutionResult


# -------------------------------------------------
# DEVELOPMENT TRACE (INTERNAL ONLY)
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    """
    Development-only tracing.

    - Printed only if ASSAULT_DEBUG_TRACE=1
    - Never part of observability
    - Never sent to EventBus
    """
    if not DEBUG_TRACE:
        return

    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# -------------------------------------------------
# ACTION RESOLUTION RESULT
# -------------------------------------------------
class ActionResolutionResult:
    """
    Container returned by resolve_action().

    new_state:
        The GameState after the action has been applied.

    combat_result:
        A CombatResolutionResult if combat happened,
        None otherwise.
    """

    def __init__(
        self,
        new_state: GameState,
        combat_result: CombatResolutionResult | None = None,
    ):
        self.new_state = new_state
        self.combat_result = combat_result


# -------------------------------------------------
# MAIN ACTION RESOLUTION ENTRY POINT
# -------------------------------------------------
def resolve_action(
    state: GameState,
    action: Action,
    combat_result: CombatResolutionResult | None = None,
) -> ActionResolutionResult:
    """
    Resolve a single action into a new GameState.

    This function:
    - Does NOT emit events
    - Does NOT consume activations
    - Does NOT print gameplay output

    It ONLY:
    - Computes the new state
    - Computes combat details (if any)
    """

    # Default: no state change
    new_state = state
    result_combat = None

    # ----------------------------------
    # MOVEMENT ACTION
    # ----------------------------------
    if isinstance(action, MoveAction):
        _trace("RESOLVE_MOVE", unit=action.unit_id)

        if action.path:
            # Movement produces a new state
            new_state = deepcopy(state)

            # Find the unit being moved
            unit = next(
                (u for u in new_state.units if u.unit_id == action.unit_id),
                None,
            )

            if unit:
                # Move to the last hex in the path
                dest = action.path[-1]
                unit.position = (dest.q, dest.r)

        # Movement never produces combat
        result_combat = None

    # ----------------------------------
    # CLOSE COMBAT (ASSAULT)
    # ----------------------------------
    elif isinstance(action, CombatAction):
        _trace("RESOLVE_COMBAT", unit=action.unit_id, mode=action.combat_mode)

        # Only ASSAULT mode supported for now
        if action.combat_mode != CombatMode.ASSAULT:
            raise NotImplementedError(
                f"Combat mode {action.combat_mode} not supported"
            )

        # -------------------------------------------------
        # IMPORTANT:
        # EventBus is NOT deepcopy-safe.
        # Detach it before copying the GameState.
        # -------------------------------------------------
        event_bus = getattr(state, "event_bus", None)
        state.event_bus = None

        # Combat always produces a new state
        new_state = deepcopy(state)

        # Restore EventBus on the new state
        new_state.event_bus = event_bus

        # Create a combat context from the new state
        ctx = new_state.create_combat_context(action)

        # Resolve close combat
        # IMPORTANT:
        # - All dice, rounds, hits, HP changes are computed here
        result_combat = resolve_close_combat(ctx)

        # -------------------------------------------------
        # OBSERVABILITY: COMBAT DETAILS BACK TO EVENT BUS
        # -------------------------------------------------
        if event_bus and result_combat:
            event_bus.emit(
                {
                    "type": "COMBAT_RESULT",
                    "payload": {
                        # We do NOT reinterpret combat_result
                        # We expose it exactly as computed
                        "combat": result_combat,
                    },
                }
            )

    # ----------------------------------
    # RETURN FINAL RESULT
    # ----------------------------------
    return ActionResolutionResult(
        new_state=new_state,
        combat_result=result_combat,
    )