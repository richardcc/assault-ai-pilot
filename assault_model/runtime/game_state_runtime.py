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
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.resolution import resolve_action

from assault_model.combat.combat_resolution import CombatResolutionResult

from assault_model.runtime.execution_context import ExecutionContext
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.combat.spotting_runtime import update_spotting
from assault_model.combat.line_of_sight import has_line_of_sight

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"
REACTION_FIRE_ENABLED = os.getenv("ASSAULT_ENABLE_REACTION_FIRE", "1") == "1"
AI_REACTION_POLICY = str(os.getenv("ASSAULT_AI_REACTION_POLICY", "balanced") or "balanced").strip().lower()
try:
    AI_REACTION_ADV_THRESHOLD = float(os.getenv("ASSAULT_AI_REACTION_ADV_THRESHOLD", "0.0"))
except Exception:
    AI_REACTION_ADV_THRESHOLD = 0.0


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
        # Monotonic state version for short-lived caches (action catalog, movement paths).
        # Must be bumped every time an action mutates the authoritative state.
        if not hasattr(self.base_state, "_cache_version"):
            self.base_state._cache_version = 0

        # activation tracking (existing)
        self.activated_units = set()

        # --- NEW: dynamic sides ---
        self.sides = self._extract_sides()
        self.active_side = self.sides[0] if self.sides else None
        # Keep a stable "first player" anchor across turns.
        self.first_player_side = self.active_side
        # Runtime-local reaction usage tracker: one reaction per reactor per turn.
        self.reaction_used_this_turn: set[str] = set()
        # Pending human reaction decision window (if any).
        self.pending_reaction: dict | None = None
        # Side controller mapping can be injected by orchestrator (human/ai).
        self.side_controller_map: dict[str, str] = {}

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

    def _start_side_for_new_turn(self):
        if not self.sides:
            return None
        anchor = self.first_player_side
        if anchor in self.sides and self.get_available_units(anchor):
            return anchor
        side = anchor if anchor in self.sides else self.sides[0]
        # Fall forward in side order until a side has available units.
        for _ in range(len(self.sides)):
            if side in self.sides and self.get_available_units(side):
                return side
            side = self._next_side(side if side in self.sides else self.sides[0])
        # If no side has available units, keep deterministic anchor.
        return anchor if anchor in self.sides else self.sides[0]

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
        self.reaction_used_this_turn.clear()
        self.pending_reaction = None
        self._sync_eliminated_activation()
        self.base_state.turn += 1

        self.sides = self._extract_sides()
        self.active_side = self._start_side_for_new_turn()

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
        self.reaction_used_this_turn.clear()
        self.pending_reaction = None
        self._sync_eliminated_activation()

        # --- NEW: reset sides each turn ---
        self.sides = self._extract_sides()
        self.active_side = self._start_side_for_new_turn()

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
            # System-level WAIT (no attacker) is used as explicit pass/end-activation
            # control path by higher-level orchestrators. It must still advance
            # activation order to avoid turn lock and stale activation markers.
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

        prev_cache_version = int(getattr(self.base_state, "_cache_version", 0))
        self.base_state = result.new_state
        self.base_state._cache_version = prev_cache_version + 1
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
        self._try_reaction_fire_on_move(
            action=action,
            attacker=attacker,
            prev_position=prev_position,
            context=context,
        )

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

    def _can_reactor_react(self, reactor, mover) -> bool:
        if reactor is None or mover is None:
            return False
        if str(getattr(reactor, "side", "")) == str(getattr(mover, "side", "")):
            return False
        if not getattr(reactor, "alive", False):
            return False
        # Reaction fire is limited to units that have not activated yet this turn.
        if getattr(reactor, "unit_id", None) in self.activated_units:
            return False
        if getattr(reactor, "unit_id", None) in self.reaction_used_this_turn:
            return False
        if not self._can_unit_act(reactor):
            return False
        if not getattr(reactor, "can_fire", True):
            return False
        if getattr(reactor, "position", None) is None or getattr(mover, "position", None) is None:
            return False
        try:
            distance = safe_hex_distance(reactor.position, mover.position)
            mode = reactor.unit_type._resolve_attack_mode(distance)
        except Exception:
            return False
        if str(mode) != "DIRECT_FIRE":
            return False
        try:
            return bool(
                has_line_of_sight(
                    attacker=reactor,
                    target=mover,
                    game_map=self.base_state.game_map,
                    terrain_config=self.scenario.terrain_config,
                )
            )
        except Exception:
            return False

    def _side_controller(self, side: str | None) -> str:
        if side is None:
            return ""
        raw = getattr(side, "value", side)
        side_norm = str(raw).strip().upper()
        # Be defensive with enum-like string representations such as "Side.IT".
        if "." in side_norm:
            side_norm = side_norm.split(".")[-1]
        side_map = getattr(self, "side_controller_map", {}) or {}
        mode = side_map.get(side_norm)
        if mode is None:
            # Lenient fallback for keys that may include enum prefixes.
            for k, v in side_map.items():
                key_norm = str(getattr(k, "value", k)).strip().upper()
                if "." in key_norm:
                    key_norm = key_norm.split(".")[-1]
                if key_norm == side_norm:
                    mode = v
                    break
        return str(mode or "").lower()

    def _interactive_match(self) -> bool:
        side_map = getattr(self, "side_controller_map", {}) or {}
        return any(str(v).lower() == "human" for v in side_map.values())

    def _should_ai_use_reaction(self, reactor, target) -> bool:
        """
        Decide whether an AI-controlled reactor should fire reaction.
        Policies:
        - always: always use if legal
        - never: always skip
        - balanced (default): use if combat advantage >= threshold
        """
        if reactor is None or target is None:
            return False
        policy = str(AI_REACTION_POLICY or "balanced").lower()
        if policy == "always":
            return True
        if policy == "never":
            return False
        try:
            advantage = float(reactor.get_combat_advantage(target))
        except Exception:
            # Conservative fallback: if we cannot estimate advantage, keep pressure.
            return True
        return advantage >= float(AI_REACTION_ADV_THRESHOLD)

    def resolve_pending_reaction(
        self,
        *,
        use_reaction: bool,
        context: ExecutionContext | None = None,
    ) -> dict:
        pending = dict(self.pending_reaction or {})
        if not pending:
            return {"resolved": False, "reason": "no_pending_reaction"}

        self.pending_reaction = None
        if not use_reaction:
            if context and context.event_bus:
                context.event_bus.emit(
                    {
                        "type": "REACTION_FIRE_SKIPPED",
                        "payload": pending,
                    }
                )
            return {"resolved": True, "used": False, "payload": pending}

        reactor_id = str(pending.get("reactor_id", ""))
        target_id = str(pending.get("target_id", ""))
        reactor = next((u for u in (self.base_state.units or []) if str(getattr(u, "unit_id", "")) == reactor_id), None)
        target = next((u for u in (self.base_state.units or []) if str(getattr(u, "unit_id", "")) == target_id), None)
        if reactor is None or target is None or not self._can_reactor_react(reactor, target):
            return {"resolved": False, "reason": "reaction_no_longer_legal", "payload": pending}

        reaction_action = RangedDirectAttack(reactor_id, target_id)
        reaction_result = resolve_action(
            state=self.base_state,
            action=reaction_action,
            combat_result=None,
            context=context,
        )
        prev_cache_version = int(getattr(self.base_state, "_cache_version", 0))
        self.base_state = reaction_result.new_state
        self.base_state._cache_version = prev_cache_version + 1
        self.activated_units.add(reactor_id)
        self.reaction_used_this_turn.add(reactor_id)
        self._sync_eliminated_activation()
        if context and context.event_bus:
            context.event_bus.emit(
                {
                    "type": "REACTION_FIRE",
                    "payload": pending,
                }
            )
        return {"resolved": True, "used": True, "payload": pending}

    def _try_reaction_fire_on_move(
        self,
        action: Action,
        attacker,
        prev_position: HexCoord | None,
        context: ExecutionContext | None = None,
    ) -> None:
        # Safe MVP: reaction windows are enabled only behind a feature flag.
        if not REACTION_FIRE_ENABLED:
            return
        if attacker is None or prev_position is None:
            return
        if not isinstance(action, (MoveAction, MoveThenFireAction, FireThenMoveAction)):
            return
        new_pos = getattr(attacker, "position", None)
        if new_pos is None:
            return
        if (
            getattr(prev_position, "q", None) == getattr(new_pos, "q", None)
            and getattr(prev_position, "r", None) == getattr(new_pos, "r", None)
        ):
            return
        # Deterministic choice: first eligible reactor by unit_id.
        enemy_units = sorted(
            [u for u in (getattr(self.base_state, "units", []) or []) if str(getattr(u, "side", "")) != str(getattr(attacker, "side", ""))],
            key=lambda u: str(getattr(u, "unit_id", "")),
        )
        reactor = next((u for u in enemy_units if self._can_reactor_react(u, attacker)), None)
        if reactor is None:
            return
        payload = {
            "reactor_id": str(reactor.unit_id),
            "target_id": str(attacker.unit_id),
            "trigger": "ENEMY_MOVES_IN_LOS",
        }
        # Ask confirmation only when the reactor side is human-controlled.
        # AI-controlled reactors must resolve reaction automatically.
        if self._side_controller(getattr(reactor, "side", None)) == "human":
            self.pending_reaction = payload
            if context and context.event_bus:
                context.event_bus.emit({"type": "REACTION_WINDOW", "payload": payload})
            return
        use_reaction = self._should_ai_use_reaction(reactor, attacker)
        if not use_reaction:
            if context and context.event_bus:
                context.event_bus.emit(
                    {
                        "type": "REACTION_FIRE_SKIPPED",
                        "payload": {**payload, "decider": "ai"},
                    }
                )
            return
        try:
            reaction_action = RangedDirectAttack(str(reactor.unit_id), str(attacker.unit_id))
            reaction_result = resolve_action(
                state=self.base_state,
                action=reaction_action,
                combat_result=None,
                context=context,
            )
            prev_cache_version = int(getattr(self.base_state, "_cache_version", 0))
            self.base_state = reaction_result.new_state
            self.base_state._cache_version = prev_cache_version + 1
            # Reaction fire consumes activation of the reactor.
            self.activated_units.add(str(reactor.unit_id))
            self.reaction_used_this_turn.add(str(reactor.unit_id))
            self._sync_eliminated_activation()
            if context and context.event_bus:
                context.event_bus.emit(
                    {
                        "type": "REACTION_FIRE",
                        "payload": payload,
                    }
                )
        except Exception as e:
            _trace("REACTION_FIRE_FAILED", error=type(e).__name__)