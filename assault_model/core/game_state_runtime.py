# assault_model/core/game_state_runtime.py

from assault_model.core.game_state import GameState
from assault_model.core.turn import TurnState
from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.resolution import resolve_action
from assault_model.combat.combat_resolution import CombatResolutionResult
from assault_model.combat.reaction_context import ReactionContext
from assault_model.combat.reaction_trigger import ReactionTrigger
from assault_model.combat.line_of_sight import has_line_of_sight

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class RuntimeGameState:
    def __init__(self, base_state: GameState):
        self.base_state = base_state
        self.turn = TurnState(turn_number=base_state.turn)

    # -------------------------------------------------
    # TURN CONTROL
    # -------------------------------------------------
    def start_turn(self) -> None:
        self.base_state.activation_state.reset(self.base_state.units)
        self.base_state.activation_state.next_unit()

    def end_turn(self) -> None:
        self.base_state.end_turn()
        self.turn = TurnState(turn_number=self.base_state.turn)

    # -------------------------------------------------
    # ACTIVATION CONSUMPTION
    # -------------------------------------------------
    def _consume_activation(self, unit):
        activated = self.base_state.activation_state.activated
        if unit not in activated:
            activated.append(unit)

    # -------------------------------------------------
    # MAIN EXECUTION ENTRY POINT
    # -------------------------------------------------
    def apply_action(
        self,
        action: Action,
        combat_result: CombatResolutionResult | None = None,
    ):
        event_bus = getattr(self.base_state, "event_bus", None)

        attacker_id = getattr(action, "unit_id", None)
        attacker = next(
            (u for u in self.base_state.units if u.unit_id == attacker_id),
            None,
        )

        # -------------------------------------------------
        # REACTION RESOLUTION
        # -------------------------------------------------
        if self.base_state.reaction_context is not None:
            ctx = self.base_state.reaction_context
            _trace(
                "REACTION_STATE_BEFORE",
                reactor=ctx.reactor.unit_id,
                moving_unit=ctx.moving_unit.unit_id,
            )

            self.base_state.clear_reaction()

            _trace(
                "REACTION_STATE_AFTER",
                reactor_alive=ctx.reactor.alive,
                moving_alive=ctx.moving_unit.alive,
            )

            if attacker:
                self._consume_activation(attacker)

            self._advance_activation()
            return None

        # -------------------------------------------------
        # INVALID ATTACKER
        # -------------------------------------------------
        if attacker is None or not attacker.alive:
            active = self.base_state.activation_state.active_unit
            if active:
                self._consume_activation(active)

            self._advance_activation()
            return None

        # -------------------------------------------------
        # WAIT
        # -------------------------------------------------
        if isinstance(action, WaitAction):
            self._consume_activation(attacker)
            self._advance_activation()
            return None

        # -------------------------------------------------
        # MOVE (⚠️ Close Combat triggers HERE)
        # -------------------------------------------------
        if isinstance(action, MoveAction):
            _trace("MOVE_START", unit=attacker.unit_id)

            for hex_coord in action.path:
                before_pos = attacker.position
                attacker.position = (hex_coord.q, hex_coord.r)

                if event_bus:
                    event_bus.emit(
                        {
                            "type": "ACTION_EFFECT",
                            "payload": {
                                "action": "MoveAction",
                                "unit_id": attacker.unit_id,
                                "from": before_pos,
                                "to": attacker.position,
                                "moved": True,
                                "hp_before": attacker.hp,
                                "hp_after": attacker.hp,
                                "hp_delta": 0,
                            },
                        }
                    )

                # ✅ DETECCIÓN DE HEX ENEMIGO → CLOSE COMBAT INMEDIATO
                enemy_in_hex = next(
                    (
                        u for u in self.base_state.units
                        if u.alive
                        and u.side != attacker.side
                        and u.position == attacker.position
                    ),
                    None,
                )

                if enemy_in_hex:
                    _trace(
                        "CLOSE_COMBAT_TRIGGER",
                        attacker=attacker.unit_id,
                        defender=enemy_in_hex.unit_id,
                    )

                    result = resolve_action(
                        state=self.base_state,
                        action=AssaultAction(
                            attacker.unit_id,
                            enemy_in_hex.unit_id,
                        ),
                        combat_result=None,
                    )

                    self.base_state = result.new_state

                    if event_bus and result.combat_result:
                        event_bus.emit(
                            {
                                "type": "COMBAT_RESULT",
                                "payload": {
                                    "combat": result.combat_result
                                },
                            }
                        )

                    self._consume_activation(attacker)
                    self._advance_activation()
                    return result

                # ❌ SOLO AQUÍ puede haber reaction (no en hex de asalto)
                for enemy in self.base_state.units:
                    if not enemy.alive or enemy.side == attacker.side:
                        continue

                    if has_line_of_sight(
                        enemy,
                        attacker,
                        self.base_state.game_map,
                    ):
                        self.base_state.enter_reaction(
                            ReactionContext(
                                trigger=ReactionTrigger.ENEMY_ENTERS_HEX,
                                reactor=enemy,
                                moving_unit=attacker,
                                entered_hex=attacker.position,
                            )
                        )
                        return None

            self._consume_activation(attacker)
            self._advance_activation()
            return None

        # -------------------------------------------------
        # OTHER ACTIONS (incl. Assault called directly)
        # -------------------------------------------------
        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
        )

        self.base_state = result.new_state

        if event_bus and result.combat_result:
            event_bus.emit(
                {
                    "type": "COMBAT_RESULT",
                    "payload": {
                        "combat": result.combat_result
                    },
                }
            )

        self._consume_activation(attacker)
        self._advance_activation()
        return result

    # -------------------------------------------------
    # ACTIVATION ADVANCE
    # -------------------------------------------------
    def _advance_activation(self):
        next_unit = self.base_state.activation_state.next_unit()
        if next_unit is None:
            self.end_turn()
            self.start_turn()