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

    # =================================================
    # TURN CONTROL
    # =================================================
    def start_turn(self) -> None:
        # =================================================
        # ✅ CLEAR SUPPRESSION AT TURN START
        # =================================================
        # At the beginning of each turn, all units remove
        # suppression state.
        #
        # Design:
        # - Simple and global
        # - Matches boardgame behavior
        # - Keeps system predictable
        #
        # IMPORTANT:
        # - Does not affect dead units
        # - Safe if unit has no suppression attribute

        for unit in self.base_state.units:
            if getattr(unit, "suppressed", False):
                unit.clear_suppression()


        self.base_state.activation_state.reset(self.base_state.units)
        self.base_state.activation_state.next_unit()

        _trace(
            "TURN_START_UNITS",
            turn=getattr(self.base_state, "turn", None),

            units=[
                {
                    "id": u.unit_id,
                    "side": u.side,
                    "alive": u.alive,

                    # ✅ Combat state
                    "hp": getattr(u, "hp", None),

                    # ✅ Suppression (core feature)
                    "suppressed": getattr(u, "suppressed", False),

                    # ✅ Future-proof (optional states)
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

        # ✅ ahora el estado vive en GameState
        self._check_match_end()

    # =================================================
    # MATCH END
    # =================================================
    def is_match_over(self) -> bool:
        return self.base_state.done

    def _check_match_end(self, context: ExecutionContext | None = None):
        """
        Check whether the match has ended and update GameState.
        """
        if self.base_state.done:
            return

        alive_units = [u for u in self.base_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}

        event_bus = context.event_bus if context else None

        # ---------------------------------------------
        # DRAW: no units alive
        # ---------------------------------------------
        if len(alive_units) == 0:
            self.base_state.done = True
            self.base_state.winner = None
            self.base_state.end_reason = "all_units_destroyed"

            if event_bus:
                event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "result": "draw",
                            "winner": None,
                            "reason": self.base_state.end_reason,
                            "turn": self.base_state.turn,
                        },
                    }
                )
            return

        # ---------------------------------------------
        # VICTORY: one side alive
        # ---------------------------------------------
        if len(alive_sides) == 1:
            winner = next(iter(alive_sides))

            self.base_state.done = True
            self.base_state.winner = winner
            self.base_state.end_reason = "last_side_standing"

            if event_bus:
                event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "result": "victory",
                            "winner": winner,
                            "reason": self.base_state.end_reason,
                            "turn": self.base_state.turn,
                        },
                    }
                )
            return

        # ---------------------------------------------
        # DRAW: max turns
        # ---------------------------------------------
        if (
            self.scenario.max_turns is not None
            and self.base_state.turn >= self.scenario.max_turns
        ):
            self.base_state.done = True
            self.base_state.winner = None
            self.base_state.end_reason = "max_turns"

            if event_bus:
                event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "result": "draw",
                            "winner": None,
                            "reason": self.base_state.end_reason,
                            "turn": self.base_state.turn,
                        },
                    }
                )

    # =================================================
    # ACTIVATION
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

            if any(not isinstance(a, WaitAction) for a in actions):
                activable.append(unit)

        return activable

    def turn_has_ended(self) -> bool:
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

        # -------------------------------------------------
        # WAIT
        # -------------------------------------------------
        if isinstance(action, WaitAction):
            self._consume_activation(attacker)
            self._advance_activation()
            return None

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

        # ✅ comprobar fin tras cada acción
        self._check_match_end(context)

        # ✅ si termina la partida → salir limpio
        if self.base_state.done:
            return result

        # -------------------------------------------------
        # CONTINUE TURN
        # -------------------------------------------------
        self._consume_activation(attacker)
        self._advance_activation()

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