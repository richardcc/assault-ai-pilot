from copy import deepcopy
import os

from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
from assault_model.actions.base import CombatAction
from assault_model.actions.combat_mode import CombatMode
from assault_model.core.game_state import GameState
from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.combat_resolution import CombatResolutionResult


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class ActionResolutionResult:
    def __init__(
        self,
        new_state: GameState,
        combat_result: CombatResolutionResult | None = None,
    ):
        self.new_state = new_state
        self.combat_result = combat_result


def resolve_action(
    state: GameState,
    action: Action,
    combat_result: CombatResolutionResult | None = None,
) -> ActionResolutionResult:

    new_state = state
    result_combat = None

    # ----------------------------------
    # MOVEMENT
    # ----------------------------------
    if isinstance(action, MoveAction):
        if action.path:
            new_state = deepcopy(state)

            unit = next(
                (u for u in new_state.units if u.unit_id == action.unit_id),
                None,
            )
            if unit:
                dest = action.path[-1]
                unit.position = (dest.q, dest.r)

        result_combat = None

    # ----------------------------------
    # CLOSE COMBAT (ASSAULT)
    # ----------------------------------
    elif isinstance(action, CombatAction):
        if action.combat_mode != CombatMode.ASSAULT:
            raise NotImplementedError(
                f"Combat mode {action.combat_mode} not supported"
            )

        new_state = deepcopy(state)

        ctx = new_state.create_combat_context(action)
        result_combat = resolve_close_combat(ctx)

    return ActionResolutionResult(
        new_state=new_state,
        combat_result=result_combat,
    )