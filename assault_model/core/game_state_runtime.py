from assault_model.core.game_state import GameState
from assault_model.core.turn import TurnState
from assault_model.actions.action import Action
from assault_model.actions.resolution import resolve_action
from assault_model.combat.combat_resolution import CombatResolutionResult

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

    def start_turn(self) -> None:
        self.base_state.activation_state.reset(self.base_state.units)
        self.base_state.activation_state.next_unit()

    # -------------------------------------------------
    # Movement helpers
    # -------------------------------------------------
    def _movement_vector(self, before, after):
        dx = after[0] - before[0]
        dy = after[1] - before[1]
        direction_map = {
            (0, -1): "NORTH",
            (0, 1): "SOUTH",
            (1, 0): "EAST",
            (-1, 0): "WEST",
            (1, -1): "NORTHEAST",
            (-1, -1): "NORTHWEST",
            (1, 1): "SOUTHEAST",
            (-1, 1): "SOUTHWEST",
        }
        return dx, dy, direction_map.get((dx, dy), "UNKNOWN")

    # -------------------------------------------------
    # Main action application
    # -------------------------------------------------
    def apply_action(
        self,
        action: Action,
        combat_result: CombatResolutionResult | None = None,
    ):
        event_bus = getattr(self.base_state, "event_bus", None)

        attacker_id = getattr(action, "unit_id", None)
        defender_id = getattr(action, "target_id", None)

        def find_unit(state, uid):
            return next((u for u in state.units if u.unit_id == uid), None)

        attacker = find_unit(self.base_state, attacker_id)

        # -------------------------------------------------
        # DEAD OR INVALID ATTACKER
        # -------------------------------------------------
        if attacker is None or not attacker.alive:
            _trace("INVALID_ATTACKER", attacker_id=attacker_id)

            if event_bus:
                event_bus.emit(
                    {
                        "type": "INVALID_ACTION",
                        "payload": {
                            "unit_id": attacker_id,
                            "reason": "unit_dead",
                        },
                    }
                )
            self._advance_activation()
            return None

        _trace(
            "APPLY_ACTION_START",
            attacker_id=attacker_id,
            defender_id=defender_id,
        )

        # -------------------------------------------------
        # BEFORE snapshot
        # -------------------------------------------------
        before = {
            "unit_id": attacker.unit_id,
            "position": attacker.position,
            "hp": attacker.hp,
        }

        # -------------------------------------------------
        # Resolve action
        # -------------------------------------------------
        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
        )
        self.base_state = result.new_state

        _trace(
            "ACTION_RESOLVED",
            attacker_alive=find_unit(self.base_state, attacker_id).alive
            if find_unit(self.base_state, attacker_id)
            else False,
        )

        # -------------------------------------------------
        # AFTER snapshot (attacker may be gone)
        # -------------------------------------------------
        after_unit = find_unit(self.base_state, attacker_id)
        after = (
            {
                "unit_id": after_unit.unit_id,
                "position": after_unit.position,
                "hp": after_unit.hp,
            }
            if after_unit
            else None
        )

        # -------------------------------------------------
        # ACTION EFFECT
        # -------------------------------------------------
        if event_bus and after:
            moved = before["position"] != after["position"]
            dx = dy = direction = None
            if moved:
                dx, dy, direction = self._movement_vector(
                    before["position"], after["position"]
                )

            event_bus.emit(
                {
                    "type": "ACTION_EFFECT",
                    "payload": {
                        "action": action.__class__.__name__,
                        "unit_id": attacker_id,
                        "from": before["position"],
                        "to": after["position"],
                        "dx": dx,
                        "dy": dy,
                        "direction": direction,
                        "hp_before": before["hp"],
                        "hp_after": after["hp"],
                        "moved": moved,
                        "hp_delta": after["hp"] - before["hp"],
                    },
                }
            )

        # -------------------------------------------------
        # CLOSE COMBAT EVENTS
        # -------------------------------------------------
        if event_bus and result.combat_result:
            _trace(
                "COMBAT_START",
                attacker_id=attacker_id,
                defender_id=defender_id,
            )

            rounds = result.combat_result.rounds

            for rr in rounds:
                event_bus.emit(
                    {
                        "type": "CLOSE_COMBAT_ROUND",
                        "payload": {
                            "round": rr.round_number,
                            "attacker_id": attacker_id,
                            "defender_id": defender_id,
                            "attacker_attack_dice": rr.attacker_attack_dice,
                            "attacker_defense_dice": rr.attacker_defense_dice,
                            "defender_attack_dice": rr.defender_attack_dice,
                            "defender_defense_dice": rr.defender_defense_dice,
                            "attacker_hp_before": rr.attacker_hp_before,
                            "attacker_hp_after": rr.attacker_hp_after,
                            "defender_hp_before": rr.defender_hp_before,
                            "defender_hp_after": rr.defender_hp_after,
                            "attacker_effects": rr.attacker_effects,
                            "defender_effects": rr.defender_effects,
                        },
                    }
                )

            event_bus.emit(
                {
                    "type": "CLOSE_COMBAT_END",
                    "payload": {
                        "attacker_id": attacker_id,
                        "defender_id": defender_id,
                        "winner": result.combat_result.winner,
                        "outcome": result.combat_result.outcome,
                    },
                }
            )

            _trace(
                "COMBAT_END",
                outcome=result.combat_result.outcome,
            )

            # -------------------------------------------------
            # ✅ REMOVE DEAD UNITS (AFTER COMBAT END)
            # -------------------------------------------------
            dead_units = [u for u in self.base_state.units if not u.alive]
            if dead_units:
                dead_ids = [u.unit_id for u in dead_units]

                _trace(
                    "REMOVE_DEAD_UNITS",
                    dead_units=dead_ids,
                )

                self.base_state.units = [
                    u for u in self.base_state.units if u.alive
                ]

                self.base_state.activation_state.reset(self.base_state.units)

                for uid in dead_ids:
                    event_bus.emit(
                        {
                            "type": "UNIT_REMOVED",
                            "payload": {
                                "unit_id": uid,
                                "reason": "killed_in_combat",
                            },
                        }
                    )

        # -------------------------------------------------
        # ✅ ACTIVATION ALWAYS ENDS HERE
        # -------------------------------------------------
        self._advance_activation()
        return result

    # -------------------------------------------------
    # Activation / turn advance
    # -------------------------------------------------
    def _advance_activation(self):
        next_unit = self.base_state.activation_state.next_unit()
        if next_unit is None:
            self.end_turn()
            self.start_turn()

    def end_turn(self) -> None:
        self.base_state.end_turn()
        self.turn = TurnState(turn_number=self.base_state.turn)