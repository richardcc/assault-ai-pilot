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
# - This module does NOT store infrastructure in GameState
# - All observability goes through ExecutionContext
# - GameState remains deepcopy-safe
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
    - Does NOT store infrastructure in state

    Observability (if any) is emitted via ExecutionContext.
    """

    event_bus = context.event_bus if context else None

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
                unit.position = dest  # ✅ keep HexCoord, do not convert to tuple

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

        new_state = deepcopy(state)

        ctx = new_state.create_combat_context(action)
        result_combat = resolve_close_combat(ctx)

        # -------------------------------------------------
        # OBSERVABILITY: COMBAT DETAILS
        # -------------------------------------------------
        if event_bus and result_combat:
            event_bus.emit(
                {
                    "type": "COMBAT_RESULT",
                    "payload": {
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