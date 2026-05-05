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
# - This module does NOT own combat rules
# - This module does NOT emit rich domain events
# - All combat-specific events are emitted by resolvers
# - Observability flows ONLY via ExecutionContext passed to resolvers
#
# DESIGN NOTE:
# - For Close Combat, this module delegates resolution
#   and passes ExecutionContext so the resolver can emit ACTION_EFFECT
# - This module must NEVER re-emit COMBAT_RESULT
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
from assault_model.runtime.execution_context import ExecutionContext

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

    NOTE:
    - combat_result is returned for internal consistency
    - Close Combat observability is handled exclusively
      by the combat resolver via ACTION_EFFECT
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
    context: ExecutionContext | None = None,
) -> ActionResolutionResult:
    """
    Resolve a single action into a new GameState.

    This function:
    - Does NOT consume activations
    - Does NOT advance turns
    - Does NOT emit rich domain events

    IMPORTANT:
    - For Close Combat, ExecutionContext MUST be passed
      to the resolver so it can emit ACTION_EFFECT
    """

    new_state = state
    result_combat = None

    # ----------------------------------
    # MOVEMENT ACTION
    # ----------------------------------
    if isinstance(action, MoveAction):
        _trace("RESOLVE_MOVE", unit=action.unit_id)

        if action.path:
            new_state = deepcopy(state)

            unit = next(
                (u for u in new_state.units if u.unit_id == action.unit_id),
                None,
            )

            if unit:
                dest = action.path[-1]
                # Keep HexCoord object intact
                unit.position = dest

        result_combat = None

    # ----------------------------------
    # CLOSE COMBAT (ASSAULT)
    # ----------------------------------
    elif isinstance(action, CombatAction):
        _trace("RESOLVE_COMBAT", unit=action.unit_id, mode=action.combat_mode)

        if action.combat_mode != CombatMode.ASSAULT:
            raise NotImplementedError(
                f"Combat mode {action.combat_mode} not supported"
            )

        # Work on a copy of the state
        new_state = deepcopy(state)

        # Create combat context from the copied state
        ctx = new_state.create_combat_context(action)

        # ✅ CRITICAL DESIGN POINT
        # Pass ExecutionContext so the resolver can emit ACTION_EFFECT.
        # This module MUST NOT emit COMBAT_RESULT.
        result_combat = resolve_close_combat(ctx, context)

    # ----------------------------------
    # RETURN FINAL RESULT
    # ----------------------------------
    return ActionResolutionResult(
        new_state=new_state,
        combat_result=result_combat,
    )
