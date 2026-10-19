from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack

from assault_model.rules.movement_rules import MovementRules
from assault_model.rules.movement_outcome import MovementOutcome

from assault_model.map.hex_utils import safe_hex_distance
from assault_model.combat.line_of_sight import has_line_of_sight
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.smoke import FireSmokeAction
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE] {tag} {payload}")


class ActionCatalog:

    def __init__(self, game_state, unit, terrain_config=None):
        self.gs = game_state
        self.unit = unit

        if terrain_config is None:
            raise ValueError(
                "ActionCatalog requires terrain_config. "
                "Use: ActionCatalog(state, unit, terrain_config)"
            )

        self.terrain_config = terrain_config


    def actions(self):
        active = self.unit

        if active is None:
            return [WaitAction("SYSTEM")]

        if not getattr(active, "alive", True):
            return []

        # Short-lived cache keyed by state version + unit tactical snapshot.
        state_version = int(getattr(self.gs, "_cache_version", 0))
        pos = getattr(active, "position", None)
        spotted = tuple(sorted(getattr(active, "spotted_enemies", []) or []))
        cache_key = (
            state_version,
            getattr(active, "unit_id", None),
            getattr(pos, "q", None),
            getattr(pos, "r", None),
            bool(getattr(active, "alive", True)),
            bool(getattr(active, "can_fire", True)),
            bool(getattr(active, "suppressed", False)),
            bool(getattr(active, "fallback", False)),
            spotted,
        )
        cache = getattr(self.gs, "_action_catalog_cache", None)
        if cache is None:
            cache = {}
            self.gs._action_catalog_cache = cache
        cached_actions = cache.get(cache_key)
        if cached_actions is not None:
            # Return a fresh list container; action objects are treated as read-only
            # by catalog consumers and tagged on selected copies downstream.
            return list(cached_actions)

        actions = []

        _trace("ACTION_CATALOG_START", unit=active.unit_id)

        # ----------------------------------
        # MOVEMENT
        # ----------------------------------
        movement_paths = MovementRules.get_legal_paths(self.gs, active)

        for mp in movement_paths:

            _trace(
                "MOVEMENT_PATH_EVAL",
                unit=active.unit_id,
                outcome=str(mp.outcome),
                target=mp.target_unit_id,
            )

            if mp.outcome == MovementOutcome.END_IN_EMPTY_HEX:
                actions.append(
                    MoveAction(
                        unit_id=active.unit_id,
                        path=mp.path,
                    )
                )

            elif mp.outcome == MovementOutcome.END_IN_ENEMY_HEX:
                target = next(
                    (u for u in self.gs.units if u.unit_id == mp.target_unit_id),
                    None,
                )

                if target is not None and target.alive:
                    actions.append(
                        AssaultAction(
                            unit_id=active.unit_id,
                            target_id=mp.target_unit_id,
                        )
                    )

        # ----------------------------------
        # RANGED FIRE
        # ----------------------------------
        actions.extend(self._ranged_fire_actions(active))
        # ----------------------------------
        # MOVE/FIRE COMPOSITES (MVP)
        # ----------------------------------
        actions.extend(self._move_fire_actions(active, movement_paths))

        # ----------------------------------
        # WAIT
        # ----------------------------------
        actions.append(WaitAction(active.unit_id))

        # ----------------------------------
        # DEBUG FINAL
        # ----------------------------------

        _trace(
            "ACTION_CATALOG_END",
            unit=active.unit_id,
            action_count=len(actions),
        )

        # ✅ ✅ NUEVO: DEBUG ACTION IDs
        if DEBUG_TRACE:
            for a in actions:
                _trace(
                    "ACTION_ID",
                    unit=active.unit_id,
                    action=getattr(a, "action_id", None)
                )

        # Cache immutable tuple container for repeated lookups in same state version.
        cache[cache_key] = tuple(actions)
        return actions

    # ==================================================
    # RANGED FIRE
    # ==================================================
    def _ranged_fire_actions(self, active):

        actions = []

        if not getattr(active, "can_fire", True):
            return actions

        # Team spotting for Rule 7.1.1 (Indirect Fire forward observers) and Rule 7.2 (Smoke)
        friendly_spotted = set()
        for u in self.gs.units:
            if u.side == active.side and getattr(u, "alive", True):
                friendly_spotted.update(getattr(u, "spotted_enemies", set()) or set())
        active_spotted = set(getattr(active, "spotted_enemies", set()) or set())

        smoke_hexes_generated = set()

        for other in self.gs.units:

            if other.side == active.side:
                continue

            if not other.alive:
                continue

            distance = safe_hex_distance(active.position, other.position)

            if not self._in_weapon_range(active, other):
                continue

            mode = active.unit_type._resolve_attack_mode(distance)

            # Direct fire requires unit's own direct spotting and direct LOS
            if mode == "DIRECT_FIRE":
                if other.unit_id not in active_spotted:
                    continue
                if not self._has_line_of_sight(active, other):
                    continue

                _trace(
                    "ACTION_ADD",
                    action="RangedDirectAttack",
                    attacker=active.unit_id,
                    target=other.unit_id,
                    mode=mode,
                )
                act = RangedDirectAttack(active.unit_id, other.unit_id)
                act.attack_mode = "DIRECT_FIRE"
                actions.append(act)

            # Rule 7.1.1: Indirect fire targets any enemy spotted by active unit OR friendly observer
            elif mode == "INDIRECT_FIRE":
                is_spotted = (other.unit_id in active_spotted) or (other.unit_id in friendly_spotted)
                if not is_spotted:
                    continue

                _trace(
                    "ACTION_ADD",
                    action="RangedIndirectAttack",
                    attacker=active.unit_id,
                    target=other.unit_id,
                    mode=mode,
                )
                act = RangedIndirectAttack(active.unit_id, (other.position.q, other.position.r))
                # Compatibility metadata used by logs/telemetry.
                act.target_id = other.unit_id
                act.attack_mode = "INDIRECT_FIRE"
                actions.append(act)

            else:
                if other.unit_id not in active_spotted:
                    continue
                if not self._has_line_of_sight(active, other):
                    continue
                act = RangedDirectAttack(active.unit_id, other.unit_id)
                act.attack_mode = "DIRECT_FIRE"
                actions.append(act)

            # Rule 7.2: If unit can fire smoke ordnance, generate FireSmokeAction on spotted target hex
            if getattr(active.unit_type, "can_fire_smoke", lambda: False)():
                target_hex = (other.position.q, other.position.r)
                is_target_spotted = (other.unit_id in active_spotted) or (other.unit_id in friendly_spotted)
                if is_target_spotted and target_hex not in smoke_hexes_generated:
                    smoke_hexes_generated.add(target_hex)
                    smoke_act = FireSmokeAction(active.unit_id, target_hex)
                    actions.append(smoke_act)

        return actions

    # ==================================================
    def _in_weapon_range(self, attacker, target):
        distance = safe_hex_distance(attacker.position, target.position)
        unit_type = getattr(attacker, "unit_type", None)
        target_type = getattr(target, "unit_type", None)
        if not unit_type or not target_type:
            return False

        if hasattr(unit_type, "has_attack_against"):
            return unit_type.has_attack_against(distance, target_type.category)

        # Fallback for mock unit objects in tests
        attack = getattr(unit_type, "_attack_raw", {}) or {}
        cat_val = target_type.category.value if hasattr(target_type.category, "value") else str(target_type.category)
        for mode, mode_data in attack.items():
            if not isinstance(mode_data, dict):
                continue
            if any(isinstance(v, dict) and "dice" in v for k, v in mode_data.items()):
                table = mode_data
            else:
                table = mode_data.get(cat_val) or mode_data.get("ALL")
                if not table and mode == "INDIRECT_FIRE":
                    table = mode_data.get("INFANTRY") or mode_data.get("VEHICLE")
            if not table:
                continue
            for key in table.keys():
                if "-" in str(key):
                    start, end = map(int, str(key).split("-"))
                    if start <= distance <= end:
                        return True
                elif int(key) == distance:
                    return True

        return False

    # ==================================================
    def _has_line_of_sight(self, attacker, target):
        return has_line_of_sight(
            attacker,
            target,
            self.gs.game_map,
            self.terrain_config
        )

    # ==================================================
    # MOVE/FIRE COMPOSITES (MVP 9.3)
    # ==================================================
    def _is_artillery_like(self, unit) -> bool:
        classification = str(getattr(getattr(unit, "unit_type", None), "classification", "") or "").upper()
        return "INDIRECT_FIRE_UNIT" in classification or "ARTILLERY" in classification

    def _half_move_limit(self, unit) -> int:
        movement = int(getattr(getattr(unit, "unit_type", None), "movement", 0) or 0)
        return max(1, (movement + 1) // 2)

    def _half_move_actions(self, movement_paths, unit):
        limit = self._half_move_limit(unit)
        moves = []
        seen_dest = set()
        cur = getattr(unit, "position", None)
        for mp in movement_paths:
            if mp.outcome != MovementOutcome.END_IN_EMPTY_HEX:
                continue
            path = list(getattr(mp, "path", []) or [])
            if not path:
                continue
            if len(path) <= limit:
                dest = path[-1]
                # Skip no-op "moves" that keep the unit in the same hex.
                if cur is not None and getattr(dest, "q", None) == getattr(cur, "q", None) and getattr(dest, "r", None) == getattr(cur, "r", None):
                    continue
                # Deduplicate by destination hex to avoid repeated entries in UI.
                key = (getattr(dest, "q", None), getattr(dest, "r", None))
                if key in seen_dest:
                    continue
                seen_dest.add(key)
                moves.append(MoveAction(unit_id=unit.unit_id, path=path))
        return moves

    def _ranged_fire_actions_from_position(self, active, position):
        if position is None:
            return []
        original_pos = active.position
        try:
            active.position = position
            return self._ranged_fire_actions(active)
        finally:
            active.position = original_pos

    def _trace_move_then_fire_diagnostics(self, active, end_pos):
        if not DEBUG_TRACE or end_pos is None:
            return
        original_pos = active.position
        try:
            active.position = end_pos
            for other in self.gs.units:
                if other.side == active.side or not other.alive:
                    continue
                spotted = other.unit_id in getattr(active, "spotted_enemies", [])
                in_range = self._in_weapon_range(active, other) if spotted else False
                los_ok = self._has_line_of_sight(active, other) if (spotted and in_range) else False
                _trace(
                    "MOVE_THEN_FIRE_CANDIDATE",
                    unit=active.unit_id,
                    move_q=getattr(end_pos, "q", None),
                    move_r=getattr(end_pos, "r", None),
                    target=other.unit_id,
                    spotted=spotted,
                    in_range=in_range,
                    los_ok=los_ok,
                )
        finally:
            active.position = original_pos

    def _move_fire_actions(self, active, movement_paths):
        if not getattr(active, "can_fire", True):
            return []
        if self._is_artillery_like(active):
            return []
        half_moves = self._half_move_actions(movement_paths, active)
        if not half_moves:
            return []

        composites = []
        seen = set()
        current_fires = self._ranged_fire_actions(active)
        # fire_then_move (fire first, then half move)
        for fire in current_fires:
            for move in half_moves:
                move_end = move.path[-1] if move.path else None
                key = (
                    "fire_then_move",
                    getattr(fire, "target_id", None),
                    getattr(fire, "target_hex", None),
                    getattr(move_end, "q", None),
                    getattr(move_end, "r", None),
                )
                if key in seen:
                    continue
                seen.add(key)
                composites.append(FireThenMoveAction(active.unit_id, fire, move.path))

        # move_then_fire (half move first, then fire from destination)
        for move in half_moves:
            end_pos = move.path[-1] if move.path else None
            self._trace_move_then_fire_diagnostics(active, end_pos)
            fires_after_move = self._ranged_fire_actions_from_position(active, end_pos)
            for fire in fires_after_move:
                key = (
                    "move_then_fire",
                    getattr(fire, "target_id", None),
                    getattr(fire, "target_hex", None),
                    getattr(end_pos, "q", None),
                    getattr(end_pos, "r", None),
                )
                if key in seen:
                    continue
                seen.add(key)
                composites.append(MoveThenFireAction(active.unit_id, move.path, fire))

        return composites
