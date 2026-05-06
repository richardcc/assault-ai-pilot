"""
RuntimeGameState is the authoritative execution engine of the game.
This class is responsible for ALL game evolution.
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
    """

    def __init__(self, base_state: GameState, scenario):
        self.base_state = base_state
        self.scenario = scenario
        self.turn = TurnState(turn_number=base_state.turn)

        self._match_over = False
        self._winner = None
        self._end_reason = None

    # =================================================
    # TURN CONTROL
    # =================================================
    def start_turn(self) -> None:
        """
        Initialize a new turn.
        Resets activation state and selects the first active unit.
        """
        self.base_state.activation_state.reset(self.base_state.units)
        self.base_state.activation_state.next_unit()

        _trace(
            "TURN_START_UNITS",
            units=[
                {
                    "id": u.unit_id,
                    "alive": u.alive,
                    "suppressed": getattr(u, "suppressed", False),
                    "fallback": getattr(u, "fallback", False),
                }
                for u in self.base_state.units
            ],
        )

    def end_turn(self) -> None:
        """
        Finalize the current turn and advance the turn counter.
        """
        self.base_state.end_turn()
        self.turn = TurnState(turn_number=self.base_state.turn)

    # =================================================
    # MATCH END
    # =================================================
    def is_match_over(self) -> bool:
        return self._match_over

    def _check_match_end(self, context: ExecutionContext | None = None):
        """
        Check whether the match has ended and emit MATCH_END if so.
        """
        if self._match_over:
            return

        alive_units = [u for u in self.base_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}

        event_bus = context.event_bus if context else None

        if len(alive_units) == 0:
            self._match_over = True
            self._winner = None
            self._end_reason = "all_units_destroyed"

            if event_bus:
                event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "result": "draw",
                            "winner": None,
                            "reason": self._end_reason,
                            "turn": self.base_state.turn,
                        },
                    }
                )
            return

        if len(alive_sides) == 1:
            self._match_over = True
            self._winner = next(iter(alive_sides))
            self._end_reason = "last_side_standing"

            if event_bus:
                event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "result": "victory",
                            "winner": self._winner,
                            "reason": self._end_reason,
                            "turn": self.base_state.turn,
                        },
                    }
                )
            return

        if (
            self.scenario.max_turns is not None
            and self.base_state.turn >= self.scenario.max_turns
        ):
            self._match_over = True
            self._winner = None
            self._end_reason = "max_turns"

            if event_bus:
                event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "result": "draw",
                            "winner": None,
                            "reason": self._end_reason,
                            "turn": self.base_state.turn,
                        },
                    }
                )

    # =================================================
    # ACTIVATION
    # =================================================
    def get_activable_units(self):
        """
        Return units that can still activate this turn.
        """
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

            if any(not isinstance(a, WaitAction) for a in actions):
                activable.append(unit)

        return activable

    def turn_has_ended(self) -> bool:
        """
        Return True if no activations remain this turn.
        """
        return not self.base_state.activation_state.remaining

    # =================================================
    # INTERNAL ACTIVATION
    # =================================================
    def _consume_activation(self, unit):
        if unit is None:
            return
        self.base_state.activation_state.consume(unit)

    def _advance_activation(self):
        self.base_state.activation_state.next_unit()

    # =================================================
    # MAIN EXECUTION
    # =================================================
    def apply_action(
        self,
        action: Action,
        combat_result: CombatResolutionResult | None = None,
        context: ExecutionContext | None = None,
    ):
        """
        Apply a single action to the game state.

        IMPORTANT:
        This class does NOT compute combat damage.
        It only adopts the mutated GameState returned by resolvers.
        """
        event_bus = context.event_bus if context else None

        attacker = next(
            (
                u
                for u in self.base_state.units
                if u.unit_id == getattr(action, "unit_id", None)
            ),
            None,
        )

        _trace(
            "APPLY_ACTION_START",
            action=action.__class__.__name__,
            attacker=attacker.unit_id if attacker else None,
        )

        prev_position = None
        if attacker and attacker.position:
            prev_position = HexCoord(attacker.position.q, attacker.position.r)

        if isinstance(action, AssaultAction) and prev_position and event_bus:
            target = next(
                (u for u in self.base_state.units if u.unit_id == action.target_id),
                None,
            )
            if target and target.position:
                assault_target_position = HexCoord(
                    target.position.q, target.position.r
                )
                event_bus.emit(
                    {
                        "type": "UNIT_MOVED",
                        "payload": {
                            "unit_id": action.unit_id,
                            "from": prev_position,
                            "to": assault_target_position,
                        },
                    }
                )

        if isinstance(action, WaitAction):
            self._consume_activation(attacker)
            self._advance_activation()
            self._check_match_end(context)
            return None

        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
            context=context,
        )

        self.base_state = result.new_state

        self._consume_activation(attacker)
        self._advance_activation()
        self._check_match_end(context)

        if event_bus and prev_position and isinstance(action, MoveAction):
            unit_after = next(
                (u for u in self.base_state.units if u.unit_id == action.unit_id),
                None,
            )
            if unit_after and unit_after.position:
                new_position = HexCoord(
                    unit_after.position.q,
                    unit_after.position.r,
                )
                event_bus.emit(
                    {
                        "type": "UNIT_MOVED",
                        "payload": {
                            "unit_id": action.unit_id,
                            "from": prev_position,
                            "to": new_position,
                        },
                    }
                )

        return result