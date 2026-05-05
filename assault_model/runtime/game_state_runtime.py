"""
RuntimeGameState is the authoritative execution engine of the game.

This class is responsible for ALL game evolution.

Responsibilities:
- Apply player / AI actions
- Resolve movement, combat, and reactions
- Manage turn lifecycle (start / end)
- Maintain activation state
- Trigger close combat and reactions
- Update GameState in a valid way
- Evaluate MATCH END conditions

Non-responsibilities:
- Does NOT decide player intent
- Does NOT choose actions
- Does NOT rank or score moves
- Does NOT interact with UI or observers directly

Design rule:
- RuntimeGameState decides WHAT HAPPENS when an action is applied.
- RuntimeGameState is the single source of truth for game rules evaluation.

Contract guarantee:
- Any change to GameState MUST pass through RuntimeGameState.
"""

from assault_model.state.game_state import GameState
from assault_model.state.turn import TurnState

from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.resolution import resolve_action
from assault_model.actions.action_catalog import ActionCatalog

from assault_model.combat.combat_resolution import CombatResolutionResult
from assault_model.combat.reaction_context import ReactionContext
from assault_model.combat.reaction_trigger import ReactionTrigger
from assault_model.combat.line_of_sight import has_line_of_sight

from assault_model.runtime.execution_context import ExecutionContext
from assault_model.map.hex_coord import HexCoord

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class RuntimeGameState:
    """
    Authoritative engine implementation.

    IMPORTANT:
    - This engine does NOT drive execution by itself.
    - It evaluates rules over world state.
    """

    def __init__(self, base_state: GameState, scenario):
        self.base_state = base_state
        self.scenario = scenario
        self.turn = TurnState(turn_number=base_state.turn)

        # --- MATCH STATE ---
        self._match_over = False
        self._winner = None
        self._end_reason = None

    # =================================================
    # TURN CONTROL (ENGINE AUTHORITY)
    # =================================================
    def start_turn(self) -> None:
        self.base_state.activation_state.reset(self.base_state.units)
        self.base_state.activation_state.next_unit()

    def end_turn(self) -> None:
        self.base_state.end_turn()
        self.turn = TurnState(turn_number=self.base_state.turn)

    # =================================================
    # MATCH END CONTRACT (ENGINE AUTHORITY)
    # =================================================
    def is_match_over(self) -> bool:
        return self._match_over

    def get_match_result(self) -> dict | None:
        if not self._match_over:
            return None

        return {
            "winner": self._winner,
            "reason": self._end_reason,
        }

    def _check_match_end(self):
        """
        Evaluate ALL match end conditions defined by the scenario.
        """

        # --- Rule 1: Last side standing ---
        alive_units = [u for u in self.base_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}

        if len(alive_sides) == 1:
            self._match_over = True
            self._winner = next(iter(alive_sides))
            self._end_reason = "last_side_standing"

            _trace(
                "MATCH_END_DECIDED",
                reason=self._end_reason,
                winner=self._winner,
            )
            return

        # --- Rule 2: Max turns reached (scenario rule) ---
        if (
            self.scenario.max_turns is not None
            and self.base_state.turn >= self.scenario.max_turns
        ):
            self._match_over = True
            self._winner = None
            self._end_reason = "max_turns_reached"

            _trace(
                "MATCH_END_DECIDED",
                reason=self._end_reason,
                turn=self.base_state.turn,
            )
            return

    # =================================================
    # ACTIVATION CONTRACT
    # =================================================
    def get_activable_units(self):
        gs = self.base_state
        catalog = ActionCatalog(gs)

        activable = []
        for unit in gs.units:
            if not unit.alive:
                continue
            if unit in gs.activation_state.activated:
                continue
            if getattr(unit, "suppressed", False):
                continue
            if getattr(unit, "fallback", False):
                continue

            prev_active = gs.activation_state.active_unit
            gs.activation_state.active_unit = unit
            try:
                actions = catalog.actions()
            finally:
                gs.activation_state.active_unit = prev_active

            real_actions = [a for a in actions if not isinstance(a, WaitAction)]
            if real_actions:
                activable.append(unit)

        return activable

    def turn_has_ended(self) -> bool:
        return len(self.get_activable_units()) == 0

    # =================================================
    # INTERNAL ACTIVATION
    # =================================================
    def _consume_activation(self, unit):
        activated = self.base_state.activation_state.activated
        if unit not in activated:
            activated.append(unit)

    def _advance_activation(self):
        next_unit = self.base_state.activation_state.next_unit()
        if next_unit is None:
            self.end_turn()
            self.start_turn()

    # =================================================
    # MAIN EXECUTION ENTRY POINT
    # =================================================
    def apply_action(
        self,
        action: Action,
        combat_result: CombatResolutionResult | None = None,
        context: ExecutionContext | None = None,
    ):
        event_bus = context.event_bus if context else None

        attacker_id = getattr(action, "unit_id", None)
        attacker = next(
            (u for u in self.base_state.units if u.unit_id == attacker_id),
            None,
        )

        # -------------------------------------------------
        # CAPTURE PRE-MOVE POSITION (IMMUTABLE SNAPSHOT)
        # -------------------------------------------------
        prev_position: HexCoord | None = None
        if isinstance(action, MoveAction) and attacker and attacker.position:
            prev_position = HexCoord(attacker.position.q, attacker.position.r)

        # -------------------------------------------------
        # REACTION RESOLUTION
        # -------------------------------------------------
        if self.base_state.reaction_context is not None:
            self.base_state.clear_reaction()
            if attacker:
                self._consume_activation(attacker)
            self._advance_activation()
            self._check_match_end()
            return None

        # -------------------------------------------------
        # INVALID ATTACKER
        # -------------------------------------------------
        if attacker is None or not attacker.alive:
            active = self.base_state.activation_state.active_unit
            if active:
                self._consume_activation(active)
            self._advance_activation()
            self._check_match_end()
            return None

        # -------------------------------------------------
        # WAIT
        # -------------------------------------------------
        if isinstance(action, WaitAction):
            self._consume_activation(attacker)
            self._advance_activation()
            self._check_match_end()
            return None

        # -------------------------------------------------
        # MOVE / COMBAT (delegated to resolver)
        # -------------------------------------------------
        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
            context=context,  # ✅ FIX: pass ExecutionContext to allow combat resolver to emit ACTION_EFFECT
        )

        self.base_state = result.new_state
        self._consume_activation(attacker)
        self._advance_activation()
        self._check_match_end()

        # -------------------------------------------------
        # DOMAIN EVENT: UNIT MOVED (TRANSITION EVENT)
        # -------------------------------------------------
        if event_bus and isinstance(action, MoveAction) and prev_position is not None:
            unit_after = next(
                (u for u in self.base_state.units if u.unit_id == action.unit_id),
                None,
            )
            if unit_after and unit_after.position:
                new_position = HexCoord(
                    unit_after.position.q,
                    unit_after.position.r,
                )

                if (
                    prev_position.q != new_position.q
                    or prev_position.r != new_position.r
                ):
                    event_bus.emit(
                        {
                            "type": "UNIT_MOVED",
                            "payload": {
                                "unit_id": unit_after.unit_id,
                                "from": prev_position,
                                "to": new_position,
                            },
                        }
                    )

        # Close Combat events are emitted exclusively by the resolver (ACTION_EFFECT)

        return result