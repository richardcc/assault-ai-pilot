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
# - For Close Combat and Ranged Combat, this module delegates resolution
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
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction

from assault_model.state.game_state import GameState
from assault_model.runtime.execution_context import ExecutionContext

from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat


from assault_model.map.hex_utils import safe_hex_distance

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
        A combat result object if combat happened,
        None otherwise.
    """

    def __init__(self, new_state: GameState, combat_result=None):
        self.new_state = new_state
        self.combat_result = combat_result


# -------------------------------------------------
# MAIN ACTION RESOLUTION ENTRY POINT
# -------------------------------------------------
def resolve_action(
    state: GameState,
    action: Action,
    combat_result=None,
    context: ExecutionContext | None = None,
) -> ActionResolutionResult:
    """
    Resolve a single action into a new GameState.

    This function:
    - Does NOT consume activations
    - Does NOT advance turns
    - Does NOT emit rich domain events

    IMPORTANT:
    - For any combat, ExecutionContext MUST be passed
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
            new_state = state

            unit = next(
                (u for u in new_state.units if u.unit_id == action.unit_id),
                None,
            )

            if unit:
                # Keep HexCoord object intact
                unit.position = action.path[-1]

    # ----------------------------------
    # COMPOSITE MOVE/FIRE ACTIONS (MVP 9.3)
    # ----------------------------------
    elif isinstance(action, MoveThenFireAction):
        _trace("RESOLVE_MOVE_THEN_FIRE", unit=action.unit_id)
        new_state = state
        # 1) move segment
        if action.move_path:
            move_action = MoveAction(action.unit_id, action.move_path)
            move_result = resolve_action(
                state=new_state,
                action=move_action,
                combat_result=combat_result,
                context=context,
            )
            new_state = move_result.new_state
        # 2) fire segment
        if action.fire_action is not None:
            fire_result = resolve_action(
                state=new_state,
                action=action.fire_action,
                combat_result=combat_result,
                context=context,
            )
            new_state = fire_result.new_state
            result_combat = fire_result.combat_result

    elif isinstance(action, FireThenMoveAction):
        _trace("RESOLVE_FIRE_THEN_MOVE", unit=action.unit_id)
        new_state = state
        # 1) fire segment
        if action.fire_action is not None:
            fire_result = resolve_action(
                state=new_state,
                action=action.fire_action,
                combat_result=combat_result,
                context=context,
            )
            new_state = fire_result.new_state
            result_combat = fire_result.combat_result
        # 2) move segment
        if action.move_path:
            move_action = MoveAction(action.unit_id, action.move_path)
            move_result = resolve_action(
                state=new_state,
                action=move_action,
                combat_result=combat_result,
                context=context,
            )
            new_state = move_result.new_state

    # ----------------------------------
    # COMBAT ACTIONS
    # ----------------------------------
    elif isinstance(action, CombatAction):
        _trace("RESOLVE_COMBAT", unit=action.unit_id, mode=action.combat_mode)

        # Always work on a copy of the state
        new_state = state

        # ------------------------------
        # CLOSE COMBAT (ASSAULT)
        # ------------------------------
        if action.combat_mode == CombatMode.ASSAULT:
            ctx = new_state.create_combat_context(action)

            # Hex objetivo del asalto (hex del defensor). Reglamento 11.1:
            # el atacante entra en el hex enemigo para iniciar el close
            # combat y lo OCUPA si elimina al defensor.
            target_hex = ctx.defender.position

            result_combat = resolve_close_combat(ctx, context)

            if (
                target_hex is not None
                and ctx.attacker.alive
                and not ctx.defender.alive
            ):
                ctx.attacker.position = target_hex

        # ------------------------------
        # RANGED DIRECT + INDIRECT FIRE
        # ------------------------------
        elif action.combat_mode in (
            CombatMode.RANGED_DIRECT,
            CombatMode.RANGED_INDIRECT,
        ):

            attacker = next(
                (u for u in new_state.units if u.unit_id == action.unit_id),
                None,
            )

            # ✅ Target para indirecto y directo
            if action.combat_mode == CombatMode.RANGED_DIRECT:
                target = next(
                    (u for u in new_state.units if u.unit_id == action.target_id),
                    None,
                )
                distance = safe_hex_distance(attacker.position, target.position)

            else:
                # ✅ INDIRECT FIRE (target_hex)
                tq, tr = action.target_hex
                target = next(
                    (
                        u for u in new_state.units
                        if u.alive
                        and u.position is not None
                        and u.position.q == tq
                        and u.position.r == tr
                    ),
                    None,
                )

                if target is None:
                    # 🔥 no hay unidad → no hay combate
                    return ActionResolutionResult(new_state=new_state, combat_result=None)

                distance = safe_hex_distance(attacker.position, action.target_hex)

            if attacker is None or target is None:
                raise RuntimeError(
                    f"Invalid attacker or target for ranged combat "
                    f"(attacker={action.unit_id})"
                )

            result_combat = resolve_ranged_combat(
                action=action,
                attacker=attacker,
                target=target,
                distance=distance,
                context=context,
            )

        # ------------------------------
        # UNKNOWN COMBAT MODE
        # ------------------------------
        else:
            raise NotImplementedError(
                f"Combat mode {action.combat_mode} not supported"
            )

    # ----------------------------------
    # RETURN FINAL RESULT
    # ----------------------------------
    return ActionResolutionResult(
        new_state=new_state,
        combat_result=result_combat,
    )