from assault_model.core.game_state import GameState
from assault_model.core.turn import TurnState
from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
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
    """
    Runtime orchestrator for the game.

    Guarantees:
    - every executed action consumes exactly one activation
    - turns always advance when activations are exhausted
    - movement can be interrupted by reaction fire
    """

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
    # MAIN ACTION APPLICATION
    # -------------------------------------------------
    def apply_action(
        self,
        action: Action,
        combat_result: CombatResolutionResult | None = None,
    ):
        event_bus = getattr(self.base_state, "event_bus", None)

        # -------------------------------------------------
        # REACTION RESOLUTION WINDOW
        # -------------------------------------------------
        if self.base_state.reaction_context is not None:
            _trace(
                "REACTION_RESOLVE",
                action=action.__class__.__name__,
                unit=getattr(action, "unit_id", None),
            )

            # cerrar ventana de reacción
            self.base_state.clear_reaction()

            # ✅ clave: la reacción CONSUME activación
            self._advance_activation()
            return None

        attacker_id = getattr(action, "unit_id", None)
        attacker = next(
            (u for u in self.base_state.units if u.unit_id == attacker_id),
            None,
        )

        # -------------------------------------------------
        # INVALID ATTACKER
        # -------------------------------------------------
        if attacker is None or not attacker.alive:
            _trace("INVALID_ATTACKER", attacker_id=attacker_id)
            self._advance_activation()
            return None

        # -------------------------------------------------
        # INTERRUPTIBLE MOVE ACTION
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
                                "dx": attacker.position[0] - before_pos[0],
                                "dy": attacker.position[1] - before_pos[1],
                                "direction": None,
                                "hp_before": attacker.hp,
                                "hp_after": attacker.hp,
                                "moved": True,
                                "hp_delta": 0,
                            },
                        }
                    )

                # -----------------------------------------
                # REACTION CHECK
                # -----------------------------------------
                for enemy in self.base_state.units:
                    if not enemy.alive:
                        continue
                    if enemy.side == attacker.side:
                        continue

                    if has_line_of_sight(
                        enemy,
                        attacker,
                        self.base_state.game_map,
                    ):
                        _trace(
                            "REACTION_TRIGGER",
                            reactor=enemy.unit_id,
                            target=attacker.unit_id,
                        )

                        self.base_state.enter_reaction(
                            ReactionContext(
                                trigger=ReactionTrigger.ENEMY_ENTERS_HEX,
                                reactor=enemy,
                                moving_unit=attacker,
                                entered_hex=attacker.position,
                            )
                        )

                        # ⛔ pausa el movimiento
                        return None

            # Movimiento finalizado sin reacción
            self._advance_activation()
            return None

        # -------------------------------------------------
        # ALL OTHER ACTIONS (ATOMIC)
        # -------------------------------------------------
        before = {
            "unit_id": attacker.unit_id,
            "position": attacker.position,
            "hp": attacker.hp,
        }

        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
        )

        self.base_state = result.new_state

        after_unit = next(
            (u for u in self.base_state.units if u.unit_id == attacker_id),
            None,
        )

        if event_bus and after_unit:
            moved = before["position"] != after_unit.position
            event_bus.emit(
                {
                    "type": "ACTION_EFFECT",
                    "payload": {
                        "action": action.__class__.__name__,
                        "unit_id": attacker_id,
                        "from": before["position"],
                        "to": after_unit.position,
                        "dx": None,
                        "dy": None,
                        "direction": None,
                        "hp_before": before["hp"],
                        "hp_after": after_unit.hp,
                        "moved": moved,
                        "hp_delta": after_unit.hp - before["hp"],
                    },
                }
            )

        # -------------------------------------------------
        # COMBAT NARRATION
        # -------------------------------------------------
        if event_bus and result.combat_result:
            for rr in result.combat_result.rounds:
                event_bus.emit(
                    {
                        "type": "CLOSE_COMBAT_ROUND",
                        "payload": rr.__dict__,
                    }
                )

            event_bus.emit(
                {
                    "type": "CLOSE_COMBAT_END",
                    "payload": {
                        "attacker_id": attacker_id,
                        "defender_id": getattr(action, "target_id", None),
                        "winner": result.combat_result.winner,
                        "outcome": result.combat_result.outcome,
                    },
                }
            )

            dead_units = [u for u in self.base_state.units if not u.alive]
            if dead_units:
                for u in dead_units:
                    event_bus.emit(
                        {
                            "type": "UNIT_REMOVED",
                            "payload": {
                                "unit_id": u.unit_id,
                                "reason": "killed_in_combat",
                            },
                        }
                    )

                self.base_state.units = [
                    u for u in self.base_state.units if u.alive
                ]
                self.base_state.activation_state.reset(self.base_state.units)

        # -------------------------------------------------
        # END ACTIVATION (SIEMPRE)
        # -------------------------------------------------
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