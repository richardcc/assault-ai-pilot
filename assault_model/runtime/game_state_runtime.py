"""
RuntimeGameState is the authoritative execution engine of the game.
Pure execution engine (no activation logic).
"""

from assault_model.state.game_state import GameState
from assault_model.state.turn import TurnState

from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.resolution import resolve_action

from assault_model.combat.combat_resolution import CombatResolutionResult

from assault_model.runtime.execution_context import ExecutionContext
from assault_model.map.hex_coord import HexCoord
from assault_model.combat.spotting_runtime import update_spotting

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class RuntimeGameState:
    """
    ✅ Pure execution engine
    ✅ No activation system
    ✅ Deterministic
    """

    def __init__(self, base_state: GameState, scenario):
        self.base_state = base_state
        self.scenario = scenario
        self.turn = TurnState(turn_number=base_state.turn)

        # ✅ NEW: control de activaciones por turno
        self.activated_units = set()

    # =================================================
    # TURN END (FIX FINAL)
    # =================================================
    def turn_has_ended(self) -> bool:
        """
        Turn ends when all eligible units have already acted.
        """

        for u in self.base_state.units:

            if not self._can_unit_act(u):
                continue

            if u.unit_id not in self.activated_units:
                return False

        return True

    # =================================================
    # ACTION GUARD
    # =================================================
    def _can_unit_act(self, unit) -> bool:
        if unit is None:
            return False
        if not unit.alive:
            return False
        if getattr(unit, "fallback", False):
            return False
        if getattr(unit, "suppressed", False):
            return False
        return True

    # =================================================
    # TURN CONTROL
    # =================================================
    def start_turn(self) -> None:
        """
        Start of turn:
        - clears suppression
        - clears fallback
        - resets activation tracker
        """

        # ✅ reset activaciones
        self.activated_units.clear()

        for unit in self.base_state.units:

            if getattr(unit, "suppressed", False):
                unit.clear_suppression()
                _trace("SUPPRESSION_RECOVERED", unit=unit.unit_id)

            if getattr(unit, "fallback", False):
                unit.clear_fallback()
                _trace("FALLBACK_RECOVERED", unit=unit.unit_id)

        _trace(
            "TURN_START_UNITS",
            turn=self.base_state.turn,
            units=[
                {
                    "id": u.unit_id,
                    "side": u.side,
                    "alive": u.alive,
                    "hp": getattr(u, "hp", None),
                }
                for u in self.base_state.units
            ],
        )

    def end_turn(self) -> None:
        self.base_state.end_turn()
        self.turn = TurnState(turn_number=self.base_state.turn)
        self._check_match_end()

    # =================================================
    # MATCH END
    # =================================================
    def is_match_over(self) -> bool:
        return self.base_state.done

    def _check_match_end(self, context: ExecutionContext | None = None):

        if self.base_state.done:
            return

        alive_units = [u for u in self.base_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}

        event_bus = context.event_bus if context else None
        
        if not alive_units:
            self.base_state.done = True
            self.base_state.winner = None
            self.base_state.end_reason = "all_units_destroyed"

            if event_bus:
                event_bus.emit({
                    "type": "MATCH_END",
                    "payload": {
                        "result": "draw",
                        "winner": None,
                        "reason": self.base_state.end_reason,
                        "turn": self.base_state.turn,
                    },
                })
            return

        if len(alive_sides) == 1:
            winner = next(iter(alive_sides))

            self.base_state.done = True
            self.base_state.winner = winner
            self.base_state.end_reason = "last_side_standing"

            if event_bus:
                event_bus.emit({
                    "type": "MATCH_END",
                    "payload": {
                        "result": "victory",
                        "winner": winner,
                        "reason": self.base_state.end_reason,
                        "turn": self.base_state.turn,
                    },
                })
            return

        if (
            self.scenario.max_turns is not None
            and self.base_state.turn >= self.scenario.max_turns
        ):
            self.base_state.done = True
            self.base_state.winner = None
            self.base_state.end_reason = "max_turns"

            if event_bus:
                event_bus.emit({
                    "type": "MATCH_END",
                    "payload": {
                        "result": "draw",
                        "winner": None,
                        "reason": self.base_state.end_reason,
                        "turn": self.base_state.turn,
                    },
                })

    # =================================================
    # MAIN EXECUTION
    # =================================================
    def apply_action(
        self,
        action: Action,
        combat_result: CombatResolutionResult | None = None,
        context: ExecutionContext | None = None,
    ):
        
        event_bus = context.event_bus if context else None
        update_spotting(self.base_state, self.scenario.terrain_config)

        attacker = next(
            (u for u in self.base_state.units if u.unit_id == getattr(action, "unit_id", None)),
            None,
        )

        _trace(
            "APPLY_ACTION_START",
            action=action.__class__.__name__,
            attacker=attacker.unit_id if attacker else None,
        )

        # ✅ marcar unidad como activada
        if attacker:
            self.activated_units.add(attacker.unit_id)

        # ✅ HARD BLOCK
        if attacker and not self._can_unit_act(attacker):

            _trace(
                "ACTION_BLOCKED",
                unit=attacker.unit_id,
            )

            return None

        prev_position = None
        if attacker and attacker.position:
            prev_position = HexCoord(attacker.position.q, attacker.position.r)

        # -------------------------------------------------
        # WAIT
        # -------------------------------------------------
        if isinstance(action, WaitAction):
            return {
                "type": "WAIT",
                "unit": attacker.unit_id if attacker else None
            }

        # -------------------------------------------------
        # APPLY ACTION
        # -------------------------------------------------
        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
            context=context,
        )

        self.base_state = result.new_state

        self._check_match_end(context)

        if self.base_state.done:
            return result

        # -------------------------------------------------
        # EVENT: MOVEMENT
        # -------------------------------------------------
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
                event_bus.emit({
                    "type": "UNIT_MOVED",
                    "payload": {
                        "unit_id": action.unit_id,
                        "from": prev_position,
                        "to": new_position,
                    },
                })
        update_spotting(self.base_state, self.scenario.terrain_config)
        return result
