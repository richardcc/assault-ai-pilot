"""
RuntimeGameState is the authoritative execution engine of the game.
Pure execution engine (no activation logic).
"""

from assault_model.state.game_state import GameState
from assault_model.state.turn import TurnState

from assault_model.actions.action import Action
from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction
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
    ✅ Deterministic

    Extended with:
    ✅ alternating activations (no hardcode)
    ✅ backward compatibility (turn_has_ended still works)
    """

    def __init__(self, base_state: GameState, scenario):
        self.base_state = base_state
        self.scenario = scenario
        self.turn = TurnState(turn_number=base_state.turn)

        # activation tracking (existing)
        self.activated_units = set()

        # --- NEW: dynamic sides ---
        self.sides = self._extract_sides()
        self.active_side = self.sides[0] if self.sides else None

    # =================================================
    # SIDES (NEW)
    # =================================================
    def _extract_sides(self):
        return sorted({
            u.side for u in self.base_state.units if u.alive
        })

    def get_available_units(self, side):
        self._sync_eliminated_activation()
        return [
            u for u in self.base_state.units
            if u.side == side
            and u.unit_id not in self.activated_units
            and self._can_unit_act(u)
        ]

    def _next_side(self, current):
        if not self.sides:
            return None
        idx = self.sides.index(current)
        return self.sides[(idx + 1) % len(self.sides)]

    def next_activation(self):
        if not self.active_side:
            return

        next_side = self._next_side(self.active_side)

        for _ in range(len(self.sides)):
            if self.get_available_units(next_side):
                self.active_side = next_side
                return
            next_side = self._next_side(next_side)

        # --- new turn ---
        self.activated_units.clear()
        self._sync_eliminated_activation()
        self.base_state.turn += 1

        self.sides = self._extract_sides()
        self.active_side = self.sides[0] if self.sides else None

    # =================================================
    # TURN END (UNCHANGED - compatibility)
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
    # ACTION GUARD (UNCHANGED)
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

    def _sync_eliminated_activation(self) -> None:
        """Dead units never take a turn; treat them as already activated."""
        for unit in self.base_state.units:
            if not unit.alive:
                self.activated_units.add(unit.unit_id)

    # =================================================
    # TURN CONTROL (MINIMAL EXTENSION)
    # =================================================
    def start_turn(self) -> None:

        self.activated_units.clear()
        self._sync_eliminated_activation()

        # --- NEW: reset sides each turn ---
        self.sides = self._extract_sides()
        self.active_side = self.sides[0] if self.sides else None

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
    # MATCH END (UNCHANGED)
    # =================================================
    def is_match_over(self) -> bool:
        return self.base_state.done

    def _check_match_end(self, context: ExecutionContext | None = None):

        if self.base_state.done:
            return

        alive_units = [u for u in self.base_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}
        outcomes = getattr(self.scenario, "victory_outcomes", None) or {}
        uses_objective_outcomes = (
            str(outcomes.get("metric", "")).strip() == "objectives_captured"
            and str(outcomes.get("timing", "")).strip() == "end_of_last_turn"
            and bool(outcomes.get("table"))
        )

        event_bus = context.event_bus if context else None

        def _finalize_vp_if_needed():
            if not self.base_state.vp_tracker:
                return
            ownership_map = {
                coords: hs.ownership
                for coords, hs in self.base_state.hex_states.items()
            }
            self.base_state.vp_tracker.finalize(ownership_map)

        def _winner_by_vp() -> str | None:
            tracker = self.base_state.vp_tracker
            if tracker is None:
                return None
            side_to_ownership = getattr(self.base_state, "side_to_ownership", {}) or {}
            if not side_to_ownership:
                return None
            side_scores = {
                side: tracker.score.get(ownership, 0)
                for side, ownership in side_to_ownership.items()
            }
            if not side_scores:
                return None
            best_score = max(side_scores.values())
            winners = [side for side, score in side_scores.items() if score == best_score]
            if len(winners) != 1:
                return None
            return winners[0]

        def _objective_outcome_winner() -> tuple[str | None, str]:
            outcomes = getattr(self.scenario, "victory_outcomes", None) or {}
            tracked_side = str(outcomes.get("tracked_side", "")).strip().upper()
            if not tracked_side:
                return None, "objective_outcome_invalid"

            points = getattr(self.base_state.victory, "points", []) if self.base_state.victory else []
            captured = 0
            for vp in points:
                hs = self.base_state.hex_states.get(vp.hex_coords)
                if hs is None:
                    continue
                owner_side = None
                for side, ownership in getattr(self.base_state, "side_to_ownership", {}).items():
                    if ownership == hs.ownership:
                        owner_side = side
                        break
                if owner_side == tracked_side:
                    captured += 1

            row_match = None
            for row in outcomes.get("table", []):
                if not isinstance(row, dict):
                    continue
                captured_range = row.get("captured", {}) or {}
                try:
                    min_cap = int(captured_range.get("min", -10**9))
                    max_cap = int(captured_range.get("max", 10**9))
                except Exception:
                    continue
                if min_cap <= captured <= max_cap:
                    row_match = row
                    break

            result_text = str((row_match or {}).get("result", "")).strip().lower()
            # Campaign table semantics:
            # - Victory only when result is explicitly "Vittoria" or "Vittoria totale".
            # - Draw on "Pareggio".
            # - Any "Sconfitta*" means tracked side loses.
            if "pareggio" in result_text or "draw" in result_text:
                # Experimental override for curriculum tuning:
                # treat campaign draw as tracked-side win.
                if os.getenv("ASSAULT_OBJECTIVE_PAREGGIO_IS_WIN", "0") == "1":
                    return tracked_side, "objective_outcome_resolved_draw_as_win"
                return None, "objective_outcome_resolved"
            if "vittoria totale" in result_text or result_text == "vittoria":
                return tracked_side, "objective_outcome_resolved"
            if "sconfitta" in result_text or "defeat" in result_text or "lose" in result_text:
                alive_sides_now = sorted({u.side for u in self.base_state.units if u.alive})
                if len(alive_sides_now) == 2 and tracked_side in alive_sides_now:
                    other = [s for s in alive_sides_now if s != tracked_side]
                    return (other[0] if other else None), "objective_outcome_resolved"
                return None, "objective_outcome_resolved"
            # Unrecognized labels default to draw to avoid accidental wins.
            return None, "objective_outcome_resolved"
        
        if not alive_units and not uses_objective_outcomes:
            _finalize_vp_if_needed()
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

        if len(alive_sides) == 1 and not uses_objective_outcomes:
            winner = next(iter(alive_sides))

            _finalize_vp_if_needed()
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
            and self.base_state.turn > self.scenario.max_turns
        ):
            _finalize_vp_if_needed()
            self.base_state.done = True
            if uses_objective_outcomes:
                winner, reason = _objective_outcome_winner()
                self.base_state.winner = winner
                self.base_state.end_reason = reason
            else:
                self.base_state.winner = _winner_by_vp()
                self.base_state.end_reason = "max_turns_vp"

            if event_bus:
                event_bus.emit({
                    "type": "MATCH_END",
                    "payload": {
                        "result": "draw" if self.base_state.winner is None else "victory",
                        "winner": self.base_state.winner,
                        "reason": self.base_state.end_reason,
                        "turn": self.base_state.turn,
                    },
                })

    # =================================================
    # MAIN EXECUTION (MINIMAL CHANGE)
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

        if attacker:
            self.activated_units.add(attacker.unit_id)

        if attacker and not self._can_unit_act(attacker):
            _trace("ACTION_BLOCKED", unit=attacker.unit_id)
            return None

        prev_position = None
        if attacker and attacker.position:
            prev_position = HexCoord(attacker.position.q, attacker.position.r)
        vp_hexes = set()
        prev_vp_owners = {}
        if self.base_state.victory:
            vp_hexes = {vp.hex_coords for vp in self.base_state.victory.points}
            prev_vp_owners = {
                coords: self.base_state.hex_states.get(coords).ownership
                for coords in vp_hexes
                if self.base_state.hex_states.get(coords) is not None
            }

        if isinstance(action, WaitAction):
            if attacker:
                self.activated_units.add(attacker.unit_id)
                self.next_activation()
            self._check_match_end(context)
            return {
                "type": "WAIT",
                "unit": attacker.unit_id if attacker else None
            }

        result = resolve_action(
            state=self.base_state,
            action=action,
            combat_result=combat_result,
            context=context,
        )

        self.base_state = result.new_state
        # Keep hex ownership (and VP current_owner in UI payload) in sync
        # immediately after actions that can change occupancy.
        self.base_state.recalculate_hex_control()
        if event_bus and vp_hexes:
            side_to_ownership = getattr(self.base_state, "side_to_ownership", {}) or {}
            ownership_to_side = {
                ownership: side
                for side, ownership in side_to_ownership.items()
            }
            vp_values = {
                vp.hex_coords: vp.per_turn
                for vp in self.base_state.victory.points
            } if self.base_state.victory else {}
            for coords in vp_hexes:
                hs = self.base_state.hex_states.get(coords)
                if hs is None:
                    continue
                before = prev_vp_owners.get(coords)
                after = hs.ownership
                if before == after:
                    continue
                prev_side = ownership_to_side.get(before)
                new_side = ownership_to_side.get(after)
                q, r = coords
                event_bus.emit({
                    "type": "VP_CAPTURED",
                    "payload": {
                        "q": q,
                        "r": r,
                        "value": int(vp_values.get(coords, 0)),
                        "previous_owner": prev_side,
                        "new_owner": new_side,
                    },
                })
        self._sync_eliminated_activation()

        # --- NEW: activation step ---
        if attacker:
            self.next_activation()
        # Objective outcomes with timing=end_of_last_turn should be evaluated
        # after activation progression (turn rollover), not mid-turn.
        self._check_match_end(context)

        if self.base_state.done:
            return result

        if event_bus and prev_position and isinstance(action, (MoveAction, MoveThenFireAction, FireThenMoveAction)):
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