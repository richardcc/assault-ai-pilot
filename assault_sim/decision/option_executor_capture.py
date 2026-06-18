from assault_model.actions.status import WaitAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.map.terrain_config import terrain_config
from assault_model.map.hex_utils import safe_hex_distance
from assault_sim.rl.tactical_options import TacticalOption


class OptionExecutorCaptureMixin:
    def _owned_vp_hexes_for_side(self, state, side: str):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or not side:
            return set()
        own_ownership = self._ownership_for_side(state, side)
        owned = set()
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                owned.add(vp.hex_coords)
        return owned

    def _threatened_owned_vp_hexes(self, state, side: str, threat_radius: int = 1):
        owned = self._owned_vp_hexes_for_side(state, side)
        if not owned:
            return set()
        enemies = [
            u
            for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) != side
            and getattr(u, "position", None) is not None
        ]
        threatened = set()
        for vp_hex in owned:
            for e in enemies:
                if safe_hex_distance(e.position, vp_hex) <= int(threat_radius):
                    threatened.add(vp_hex)
                    break
        return threatened

    def _best_defend_owned_vp_action(self, state, unit, attack_mode):
        if unit is None or getattr(unit, "position", None) is None:
            return None, None
        threatened_vps = self._threatened_owned_vp_hexes(state, getattr(unit, "side", None), threat_radius=1)
        if not threatened_vps:
            return None, None
        # Soft guardrail: only defend with this unit if it is locally relevant
        # (close enough to intervene) and threat is critical.
        nearest_threatened = min(safe_hex_distance(unit.position, vp) for vp in threatened_vps)
        if nearest_threatened > 2:
            return None, None
        enemies = [
            u
            for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) != getattr(unit, "side", None)
            and getattr(u, "position", None) is not None
        ]
        critical_threat = any(
            safe_hex_distance(e.position, vp) <= 0
            for vp in threatened_vps
            for e in enemies
        )
        if not critical_threat:
            return None, None

        actions = self._get_unit_actions(state, unit)
        best_move = None
        best_move_score = float("-inf")
        for a in actions:
            if getattr(getattr(a, "action_type", None), "category", None) != ActionCategory.MOVEMENT:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            end = path[-1]
            end_t = (end.q, end.r)
            d_before = min(safe_hex_distance(unit.position, vp) for vp in threatened_vps)
            d_after = min(safe_hex_distance(end, vp) for vp in threatened_vps)
            if d_after >= d_before and end_t not in threatened_vps:
                continue
            terrain_score = self._terrain_tactical_score(state, unit, end)
            score = (50.0 if end_t in threatened_vps else 0.0) + (d_before - d_after) * 8.0 + 0.2 * float(terrain_score)
            if score > best_move_score:
                best_move_score = score
                best_move = a

        attacks = [a for a in actions if self._is_attack_action(a)]
        defend_attacks = []
        for a in attacks:
            target = self._resolve_action_target(state, a)
            if target is None or not getattr(target, "alive", False) or getattr(target, "position", None) is None:
                continue
            if any(safe_hex_distance(target.position, vp) <= 1 for vp in threatened_vps):
                defend_attacks.append(a)
        best_attack = self._best_attack(defend_attacks, state=state, unit=unit) if defend_attacks else None

        if best_move is not None and best_move_score >= 58.0:
            best_move.rl_capture_fallback_reason = "defend_owned_vp_move"
            best_move.rl_capture_move_block_profile = "owned_vp_threatened"
            return best_move, TacticalOption.ADVANCE
        if best_attack is not None:
            best_attack.rl_capture_fallback_to_attack = True
            best_attack.rl_capture_fallback_reason = "defend_owned_vp_attack"
            best_attack.rl_capture_move_block_profile = "owned_vp_threatened"
            return best_attack, TacticalOption.ATTACK
        if best_move is not None:
            best_move.rl_capture_fallback_reason = "defend_owned_vp_reposition"
            best_move.rl_capture_move_block_profile = "owned_vp_threatened"
            return best_move, TacticalOption.ADVANCE
        return None, None

    def _objective_target_hex(self, state, unit):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        locked = self._locked_capture_focus_hex(state, unit)
        if locked is not None:
            return locked
        own_ownership = self._ownership_for_side(state, unit.side)
        best = None
        best_score = float("-inf")
        allies = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) == getattr(unit, "side", None)
            and getattr(u, "position", None) is not None
            and getattr(u, "unit_id", None) != getattr(unit, "unit_id", None)
        ]
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            owned_by_self = hs is not None and hs.ownership == own_ownership
            need = 0.0 if owned_by_self else 1.0
            dist = safe_hex_distance(unit.position, vp.hex_coords)
            ally_pressure = sum(1 for a in allies if safe_hex_distance(a.position, vp.hex_coords) <= 2)
            score = need * 120.0 + float(getattr(vp, "per_turn", 0)) * 2.0 - float(dist)
            # Stronger anti-concentration near the same VP to reduce local jams
            # and increase legal step-in opportunities across multiple fronts.
            score -= 6.0 * float(ally_pressure)
            if ally_pressure >= 2:
                score -= 10.0
            if owned_by_self and dist == 0:
                score -= 6.0
            if score > best_score:
                best_score = score
                best = vp.hex_coords
        return best

    def _has_uncaptured_objective(self, state, unit) -> bool:
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        own_ownership = self._ownership_for_side(state, unit.side)
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is None:
                continue
            if hs.ownership != own_ownership:
                return True
        return False

    def _has_uncaptured_objective_for_side(self, state, side: str) -> bool:
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or not side:
            return False
        own_ownership = self._ownership_for_side(state, side)
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is None:
                continue
            if hs.ownership != own_ownership:
                return True
        return False

    def _is_target_on_enemy_or_neutral_vp(self, state, unit, target) -> bool:
        if target is None or getattr(target, "position", None) is None:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        pos = (target.position.q, target.position.r)
        vp_hexes = {vp.hex_coords for vp in points}
        if pos not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, unit.side)
        hs = state.hex_states.get(pos)
        return hs is None or hs.ownership != own_ownership

    def _is_target_on_owned_vp(self, state, unit, target) -> bool:
        if target is None or getattr(target, "position", None) is None:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        pos = (target.position.q, target.position.r)
        vp_hexes = {vp.hex_coords for vp in points}
        if pos not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, unit.side)
        hs = state.hex_states.get(pos)
        return hs is not None and hs.ownership == own_ownership

    def _is_target_near_uncaptured_vp(self, state, unit, target, max_dist: int = 1) -> bool:
        if target is None or getattr(target, "position", None) is None or unit is None:
            return False
        d = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, target.position)
        return d is not None and float(d) <= float(max_dist)

    def _is_capture_emergency(self, state, unit) -> bool:
        if unit is None:
            return False
        hp = float(getattr(unit, "hp", 0) or 0)
        max_hp = float(getattr(getattr(unit, "unit_type", None), "max_strength", 0) or 0)
        suppressed = bool(getattr(unit, "suppressed", False))
        enemies = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) != getattr(unit, "side", None)
            and getattr(u, "position", None) is not None
            and getattr(unit, "position", None) is not None
        ]
        close_threat = any(safe_hex_distance(unit.position, e.position) <= 2 for e in enemies)
        critical_hp = hp <= max(1.0, max_hp * 0.20) if max_hp > 0 else hp <= 1.0
        return bool((critical_hp and close_threat) or (suppressed and close_threat))

    def _best_step_into_uncaptured_vp(self, state, unit):
        if unit is None or getattr(unit, "position", None) is None:
            return None
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        own_ownership = self._ownership_for_side(state, unit.side)
        vp_hexes = {vp.hex_coords for vp in points}
        actions = self._get_unit_actions(state, unit)
        best = None
        best_score = float("-inf")
        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            new_pos = path[-1]
            pos_t = (new_pos.q, new_pos.r)
            if pos_t not in vp_hexes:
                continue
            hs = state.hex_states.get(pos_t)
            if hs is not None and hs.ownership == own_ownership:
                continue
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = 1000.0 + terrain_score
            if score > best_score:
                best_score = score
                best = a
        return best

    def _best_stepin_setup_move(self, state, unit):
        """Pick a movement that prepares a legal VP step-in next activation."""
        if unit is None or getattr(unit, "position", None) is None:
            return None, None
        dist_before = self._nearest_uncaptured_vp_dist(state, unit)
        actions = self._get_unit_actions(state, unit)
        best = None
        best_score = float("-inf")
        best_after = None
        for m in actions:
            if getattr(getattr(m, "action_type", None), "category", None) != ActionCategory.MOVEMENT:
                continue
            path = getattr(m, "path", None)
            if not path:
                continue
            end = path[-1]
            if self._is_reversal_move(unit, end) and not self._is_uncaptured_vp_hex(state, unit.side, end):
                continue
            dist_after = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, end)
            if dist_after is None:
                continue
            # Primary goal: be adjacent (dist=1) to enable step-in on next action.
            score = -10.0 * abs(float(dist_after) - 1.0)
            if dist_before is not None and float(dist_after) < float(dist_before):
                score += 2.5
            elif dist_before is not None and float(dist_after) == float(dist_before):
                score -= 0.8
            terrain_score = self._terrain_tactical_score(state, unit, end)
            enemy_pressure = self._enemy_pressure_at_pos(state, unit.side, end, radius=3)
            score += 0.2 * float(terrain_score) - 0.5 * float(enemy_pressure)
            if self._is_uncaptured_vp_hex(state, unit.side, end):
                score += 20.0
            if score > best_score:
                best_score = score
                best = m
                best_after = dist_after
        if best is None:
            return None, None
        # Hard validity gate: setup is only valid if we end adjacent to an
        # uncaptured VP (distance 1), otherwise this is just lateral staging.
        if best_after is None or float(best_after) > 1.0:
            return None, None
        return best, best_after

    def _is_uncaptured_vp_hex(self, state, side: str, pos) -> bool:
        if pos is None or not side:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        vp_hexes = {vp.hex_coords for vp in points}
        key = (getattr(pos, "q", None), getattr(pos, "r", None))
        if key not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, side)
        hs = state.hex_states.get(key)
        return hs is None or hs.ownership != own_ownership

    def _is_uncaptured_vp_coords(self, state, side: str, coords) -> bool:
        if coords is None or not side:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        vp_hexes = {vp.hex_coords for vp in points}
        key = (coords[0], coords[1])
        if key not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, side)
        hs = state.hex_states.get(key)
        return hs is None or hs.ownership != own_ownership

    def _nearest_uncaptured_vp_dist(self, state, unit):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or unit is None or getattr(unit, "position", None) is None:
            return None
        own_ownership = self._ownership_for_side(state, unit.side)
        best = None
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                continue
            d = safe_hex_distance(unit.position, vp.hex_coords)
            if best is None or d < best:
                best = d
        return best

    def _nearest_uncaptured_vp_ring_dist_from_pos(self, state, side: str, pos):
        d = self._nearest_uncaptured_vp_dist_from_pos(state, side, pos)
        if d is None:
            return None
        return max(0.0, float(d) - 1.0)

    def _enemy_pressure_at_pos(self, state, side: str, pos, radius: int = 3) -> float:
        if pos is None or not side:
            return 0.0
        pressure = 0.0
        for e in getattr(state, "units", []) or []:
            if not getattr(e, "alive", False):
                continue
            if getattr(e, "side", None) == side:
                continue
            epos = getattr(e, "position", None)
            if epos is None:
                continue
            d = safe_hex_distance(pos, epos)
            if d is None or d > radius:
                continue
            pressure += 1.0 / max(1.0, float(d))
        return float(pressure)

    def _best_capture_staging_move(self, state, unit):
        actions = self._get_unit_actions(state, unit)
        moves = [a for a in actions if getattr(getattr(a, "action_type", None), "category", None) == ActionCategory.MOVEMENT]
        if not moves:
            debug = {
                "move_candidates_total": 0,
                "progress_candidates": 0,
                "equal_candidates": 0,
                "increase_candidates": 0,
                "reversal_filtered": 0,
                "progress_available": False,
                "selected_reason": "no_movement_actions",
                "selected_dist_delta": None,
                "suspected_progress_miss": False,
            }
            return None, "no_movement_actions", None, None, debug

        dist_before = self._nearest_uncaptured_vp_dist(state, unit)
        ring_before = self._nearest_uncaptured_vp_ring_dist_from_pos(state, unit.side, unit.position)
        uid = getattr(unit, "unit_id", None)
        prev_pos = self._prev_pos_by_unit.get(uid) if uid else None
        best_any = None
        best_any_score = float("-inf")
        best_non_worse = None
        best_non_worse_score = float("-inf")
        best_progress = None
        best_progress_score = float("-inf")
        saw_equal = False
        saw_increase_only = True
        progress_candidates = 0
        equal_candidates = 0
        increase_candidates = 0
        reversal_filtered = 0
        legal_move_candidates = 0

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue
            end = path[-1]
            if self._is_reversal_move(unit, end) and not self._is_uncaptured_vp_hex(state, unit.side, end):
                reversal_filtered += 1
                continue
            dist_after = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, end)
            if dist_after is None:
                continue
            legal_move_candidates += 1
            ring_after = self._nearest_uncaptured_vp_ring_dist_from_pos(state, unit.side, end)
            enemy_pressure = self._enemy_pressure_at_pos(state, unit.side, end, radius=3)
            terrain_score = self._terrain_tactical_score(state, unit, end)
            score = -float(dist_after) + 0.3 * terrain_score - 0.35 * float(enemy_pressure)
            if ring_after is not None:
                score -= 0.8 * float(ring_after)
            if ring_before is not None and ring_after is not None:
                if float(ring_after) < float(ring_before):
                    score += 2.0
                elif float(ring_after) == float(ring_before):
                    score -= 0.6
            if (
                dist_before is not None
                and float(dist_before) <= 3.0
                and float(dist_after) == float(dist_before)
            ):
                score -= 1.5
                end_t = (getattr(end, "q", None), getattr(end, "r", None))
                if prev_pos is not None and end_t == prev_pos:
                    score -= 1.5
            if self._is_reversal_move(unit, end):
                score -= 8.0
            if score > best_any_score:
                best_any_score = score
                best_any = (m, dist_after, score)
            if dist_before is not None and dist_after < dist_before:
                progress_candidates += 1
                saw_increase_only = False
                if score > best_progress_score:
                    best_progress_score = score
                    best_progress = (m, dist_after, score)
                if score > best_non_worse_score:
                    best_non_worse_score = score
                    best_non_worse = (m, dist_after, score)
            elif dist_before is not None and dist_after == dist_before:
                equal_candidates += 1
                saw_equal = True
                saw_increase_only = False
                if score > best_non_worse_score:
                    best_non_worse_score = score
                    best_non_worse = (m, dist_after, score)
            elif dist_before is not None and dist_after > dist_before:
                increase_candidates += 1

        def _build_debug(selected_reason: str, selected_after):
            dist_delta = None
            if dist_before is not None and selected_after is not None:
                dist_delta = float(dist_before) - float(selected_after)
            progress_available = progress_candidates > 0
            suspected_progress_miss = bool(progress_available and selected_reason != "objective_progress_move")
            return {
                "move_candidates_total": int(legal_move_candidates),
                "progress_candidates": int(progress_candidates),
                "equal_candidates": int(equal_candidates),
                "increase_candidates": int(increase_candidates),
                "reversal_filtered": int(reversal_filtered),
                "progress_available": bool(progress_available),
                "selected_reason": str(selected_reason or ""),
                "selected_dist_delta": dist_delta,
                "suspected_progress_miss": bool(suspected_progress_miss),
            }

        if best_progress is not None:
            move, dist_after, _ = best_progress
            return move, "objective_progress_move", dist_before, dist_after, _build_debug("objective_progress_move", dist_after)
        if best_non_worse is not None:
            move, dist_after, _ = best_non_worse
            if dist_before is not None and dist_after < dist_before:
                return move, "objective_progress_move", dist_before, dist_after, _build_debug("objective_progress_move", dist_after)
            if dist_before is not None and dist_after == dist_before:
                return move, "objective_staging_move", dist_before, dist_after, _build_debug("objective_staging_move", dist_after)
            return move, "objective_staging_move", dist_before, dist_after, _build_debug("objective_staging_move", dist_after)
        if best_any is not None:
            move, dist_after, _ = best_any
            if saw_increase_only and dist_before is not None:
                return move, "all_moves_increase_distance", dist_before, dist_after, _build_debug("all_moves_increase_distance", dist_after)
            if saw_equal:
                return move, "only_equal_distance_moves", dist_before, dist_after, _build_debug("only_equal_distance_moves", dist_after)
            return move, "no_progress_move_available", dist_before, dist_after, _build_debug("no_progress_move_available", dist_after)
        return None, "no_movement_actions", dist_before, None, _build_debug("no_movement_actions", None)

    def _attach_capture_progress_debug(self, action, debug_snapshot):
        if action is None:
            return
        debug = debug_snapshot or {}
        action.rl_capture_move_candidates_total = int(debug.get("move_candidates_total", 0) or 0)
        action.rl_capture_progress_candidates = int(debug.get("progress_candidates", 0) or 0)
        action.rl_capture_equal_candidates = int(debug.get("equal_candidates", 0) or 0)
        action.rl_capture_increase_candidates = int(debug.get("increase_candidates", 0) or 0)
        action.rl_capture_reversal_filtered = int(debug.get("reversal_filtered", 0) or 0)
        action.rl_capture_progress_available = bool(debug.get("progress_available", False))
        action.rl_capture_selected_move_reason = str(debug.get("selected_reason", "") or "")
        action.rl_capture_selected_dist_delta = debug.get("selected_dist_delta", None)
        action.rl_capture_suspected_progress_miss = bool(debug.get("suspected_progress_miss", False))

    def _attach_vp_entry_debug(self, action, legal_stepin: bool, selected_stepin: bool, block_reason: str):
        if action is None:
            return
        action.rl_vp_stepin_legal = bool(legal_stepin)
        action.rl_vp_stepin_selected = bool(selected_stepin)
        action.rl_vp_stepin_block_reason = str(block_reason or "")
        if not hasattr(action, "rl_vp_nearest_uncaptured_dist"):
            action.rl_vp_nearest_uncaptured_dist = None
        if not hasattr(action, "rl_vp_opening_attack_candidates_count"):
            action.rl_vp_opening_attack_candidates_count = 0

    def _has_vp_attack_opportunity(self, state, unit) -> bool:
        if unit is None:
            return False
        actions = self._get_unit_actions(state, unit)
        attacks = [a for a in actions if self._is_attack_action(a)]
        if not attacks:
            return False
        for a in attacks:
            target = self._resolve_action_target(state, a)
            if self._is_target_on_enemy_or_neutral_vp(state, unit, target):
                return True
        return False

    def _move_closer(self, state, unit, capture_strict: bool = False):
        actions = self._get_unit_actions(state, unit)
        objective_target = self._objective_target_hex(state, unit)
        enemies = [u for u in state.units if u.side != unit.side and u.alive]
        if objective_target is None and not enemies:
            return WaitAction(unit.unit_id)
        if objective_target is None:
            objective_target = min(enemies, key=lambda e: safe_hex_distance(unit.position, e.position)).position

        best = None
        best_score = float("-inf")
        best_non_worse = None
        best_non_worse_score = float("-inf")
        dist_before_target = None
        if objective_target is not None and getattr(unit, "position", None) is not None:
            dist_before_target = safe_hex_distance(unit.position, objective_target)

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            new_pos = path[-1]
            if self._is_reversal_move(unit, new_pos) and not self._is_uncaptured_vp_hex(state, unit.side, new_pos):
                continue
            d = safe_hex_distance(new_pos, objective_target)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            if capture_strict:
                score = -100.0 * float(d) + 0.1 * self._MOVE_CFG.advance_terrain_weight * terrain_score
            else:
                score = -float(d) + self._MOVE_CFG.advance_terrain_weight * terrain_score
            if self._is_uncaptured_vp_hex(state, unit.side, new_pos):
                score += 120.0
            if self._is_reversal_move(unit, new_pos):
                score -= 8.0
            if score > best_score:
                best = a
                best_score = score
            if capture_strict and dist_before_target is not None and d <= dist_before_target and score > best_non_worse_score:
                best_non_worse = a
                best_non_worse_score = score

        if capture_strict and best_non_worse is not None:
            return best_non_worse
        return best or WaitAction(unit.unit_id)

    def _flank_move(self, state, unit):
        actions = self._get_unit_actions(state, unit)
        objective_target = self._objective_target_hex(state, unit)
        enemies = [u for u in state.units if u.side != unit.side and u.alive]
        if objective_target is None and not enemies:
            return WaitAction(unit.unit_id)
        if objective_target is None:
            objective_target = min(enemies, key=lambda e: safe_hex_distance(unit.position, e.position)).position

        best = None
        best_score = float("-inf")
        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            new_pos = path[-1]
            if self._is_reversal_move(unit, new_pos) and not self._is_uncaptured_vp_hex(state, unit.side, new_pos):
                continue
            dist = safe_hex_distance(new_pos, objective_target)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = -dist + self._MOVE_CFG.flank_terrain_weight * terrain_score
            if self._is_reversal_move(unit, new_pos):
                score -= 8.0
            if 1 < dist <= 3:
                score += 3
            if score > best_score:
                best_score = score
                best = a
        return best or self._move_closer(state, unit)

    def _capture_priority_action(self, state, unit, attack_mode):
        self._capture_decision_seq += 1
        decision_seq = int(self._capture_decision_seq)
        step_into_vp_candidate = self._best_step_into_uncaptured_vp(state, unit)
        has_legal_stepin = step_into_vp_candidate is not None
        nearest_vp_d = self._nearest_uncaptured_vp_dist(state, unit)
        default_block_reason = ""
        if not has_legal_stepin:
            if nearest_vp_d is None or float(nearest_vp_d) >= 999.0:
                default_block_reason = "no_objective_reachable"
            elif float(nearest_vp_d) <= 2.0:
                default_block_reason = "no_legal_stepin_near_vp"
            else:
                default_block_reason = "no_legal_stepin"
        uid = getattr(unit, "unit_id", None)
        if uid:
            if default_block_reason == "no_legal_stepin_near_vp":
                self._capture_no_stepin_near_streak_by_unit[uid] = int(self._capture_no_stepin_near_streak_by_unit.get(uid, 0)) + 1
            else:
                self._capture_no_stepin_near_streak_by_unit[uid] = 0
        open_window_throttle_ok = True
        if uid:
            last_seq = int(self._capture_open_window_last_seq_by_unit.get(uid, -999999))
            open_window_throttle_ok = (decision_seq - last_seq) >= 2
        open_window_quality_ok = True
        if uid:
            cooldown_until = int(self._capture_open_window_cooldown_until_seq_by_unit.get(uid, -999999))
            open_window_quality_ok = decision_seq > cooldown_until

        if self._is_capture_emergency(state, unit):
            action = self.heuristic.choose_action(state, unit, TacticalOption.RETREAT)
            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                action = WaitAction(unit.unit_id)
            if action is not None:
                action.rl_capture_fallback_reason = "capture_emergency"
                action.rl_capture_move_block_profile = "emergency_blocked"
                self._attach_vp_entry_debug(action, has_legal_stepin, False, "capture_emergency")
            return action or WaitAction(unit.unit_id), TacticalOption.RETREAT

        step_into_vp = step_into_vp_candidate
        if step_into_vp is not None:
            d_before = self._nearest_uncaptured_vp_dist(state, unit)
            step_into_vp.rl_capture_fallback_reason = "step_into_uncaptured_vp"
            step_into_vp.rl_capture_move_block_profile = "step_into_uncaptured_vp"
            step_into_vp.rl_capture_target_dist_before = d_before
            step_into_vp.rl_capture_target_dist_after = 0
            self._attach_vp_entry_debug(step_into_vp, True, True, "")
            return step_into_vp, TacticalOption.ADVANCE

        move, move_reason, dist_before, dist_after, move_debug = self._best_capture_staging_move(state, unit)
        if not move_reason:
            move_reason = "no_movement_actions"
        if (
            not has_legal_stepin
            and nearest_vp_d is not None
            and 2.0 <= float(nearest_vp_d) <= 3.0
            and move_reason in {"objective_staging_move", "all_moves_increase_distance", "no_progress_move_available"}
        ):
            setup_move, setup_after = self._best_stepin_setup_move(state, unit)
            if setup_move is not None:
                setup_move.rl_capture_fallback_reason = "forced_stepin_setup_move"
                setup_move.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                setup_move.rl_capture_target_dist_before = dist_before
                setup_move.rl_capture_target_dist_after = setup_after
                self._attach_capture_progress_debug(setup_move, move_debug)
                self._attach_vp_entry_debug(
                    setup_move,
                    has_legal_stepin,
                    False,
                    default_block_reason or move_reason or "forced_stepin_setup_move",
                )
                setup_move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                setup_move.rl_vp_opening_attack_candidates_count = 0
                return setup_move, TacticalOption.ADVANCE
        if (
            uid
            and bool(self._capture_open_window_pending_followup_by_unit.get(uid, False))
            and move is not None
            and dist_before is not None
            and dist_after is not None
            and float(dist_after) <= float(dist_before)
        ):
            move.rl_capture_fallback_reason = "post_open_window_followup_advance"
            move.rl_capture_move_block_profile = move_reason or "objective_staging_move"
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            move.rl_post_open_window_followup_advance = True
            move.rl_post_open_window_followup_success = bool(float(dist_after) < float(dist_before))
            self._attach_capture_progress_debug(move, move_debug)
            self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason or "post_open_window_followup_advance")
            move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
            move.rl_vp_opening_attack_candidates_count = 0
            self._capture_open_window_pending_followup_by_unit[uid] = False
            return move, TacticalOption.ADVANCE
        if uid and move_reason == "objective_staging_move":
            self._capture_staging_streak_by_unit[uid] = int(self._capture_staging_streak_by_unit.get(uid, 0)) + 1
        elif uid:
            self._capture_staging_streak_by_unit[uid] = 0

        actions = ActionCatalog(state, unit, terrain_config).actions()
        attacks = [a for a in actions if self._is_attack_action(a)]
        prefer_mobility_near_vp = (
            nearest_vp_d is not None
            and float(nearest_vp_d) <= 3.0
            and move is not None
        )
        if attacks and uid:
            staging_streak = int(self._capture_staging_streak_by_unit.get(uid, 0))
            vp_dist_unknown = nearest_vp_d is None or float(nearest_vp_d) >= 999.0
            if (
                move_reason == "objective_staging_move"
                and (vp_dist_unknown or float(nearest_vp_d) <= 3.0)
                and staging_streak >= 2
                and not prefer_mobility_near_vp
            ):
                forced = self._best_attack(attacks, state=state, unit=unit)
                if forced is not None:
                    forced.rl_capture_fallback_to_attack = True
                    forced.rl_capture_fallback_reason = "forced_attack_after_staging_loop"
                    forced.rl_capture_move_block_profile = move_reason
                    forced.rl_capture_target_dist_before = dist_before
                    forced.rl_capture_target_dist_after = dist_after
                    self._attach_capture_progress_debug(forced, move_debug)
                    return forced, TacticalOption.ATTACK
        if attacks:
            vp_relevant_attacks = []
            vp_opening_attacks = []
            unit_role = self._local_role_kind(state, unit)
            for a in attacks:
                target = self._resolve_action_target(state, a)
                if target is None or not getattr(target, "alive", False):
                    continue
                target_on_vp = self._is_target_on_enemy_or_neutral_vp(state, unit, target)
                target_on_owned_vp = self._is_target_on_owned_vp(state, unit, target)
                target_near_uncaptured_vp = self._is_target_near_uncaptured_vp(state, unit, target, max_dist=1)
                if target_on_vp or target_on_owned_vp:
                    vp_relevant_attacks.append(a)
                if target_on_vp or target_on_owned_vp or target_near_uncaptured_vp:
                    vp_opening_attacks.append(a)
            if (
                nearest_vp_d is not None
                and float(nearest_vp_d) <= 3.0
                and (
                    move_reason in {"objective_staging_move", "all_moves_increase_distance", "no_progress_move_available"}
                    or (
                        default_block_reason == "no_legal_stepin_near_vp"
                        and int(self._capture_no_stepin_near_streak_by_unit.get(uid, 0) if uid else 0) >= 1
                    )
                )
                and vp_opening_attacks
                and open_window_throttle_ok
                and open_window_quality_ok
            ):
                open_window = self._best_attack(vp_opening_attacks, state=state, unit=unit)
                if open_window is not None:
                    open_window.rl_capture_fallback_to_attack = True
                    open_window.rl_capture_fallback_reason = "forced_attack_open_vp_window"
                    open_window.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                    open_window.rl_capture_target_dist_before = dist_before
                    open_window.rl_capture_target_dist_after = dist_after
                    open_window.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(open_window, move_debug)
                    self._attach_vp_entry_debug(open_window, has_legal_stepin, False, default_block_reason or move_reason or "forced_attack_open_vp_window")
                    open_window.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    if uid:
                        self._capture_open_window_last_seq_by_unit[uid] = decision_seq
                        self._capture_open_window_pending_followup_by_unit[uid] = True
                        exp_dmg = float(getattr(open_window, "rl_attack_expected_damage", 0.0) or 0.0)
                        if exp_dmg <= 0.05:
                            self._capture_open_window_cooldown_until_seq_by_unit[uid] = decision_seq + int(self._capture_open_window_cooldown_steps)
                    return open_window, TacticalOption.ATTACK
            if nearest_vp_d is not None and float(nearest_vp_d) <= 2.0:
                # Near VP, do not accept lateral/no-progress staging as "good enough".
                # Keep only objective_progress_move in this strict close-range band.
                if move is not None and move_reason == "objective_progress_move":
                    move.rl_capture_fallback_reason = move_reason
                    move.rl_capture_move_block_profile = move_reason
                    move.rl_capture_target_dist_before = dist_before
                    move.rl_capture_target_dist_after = dist_after
                    move.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(move, move_debug)
                    self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason)
                    move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    return move, TacticalOption.ADVANCE
            if (
                move_reason == "objective_staging_move"
                and nearest_vp_d is not None
                and float(nearest_vp_d) <= 2.0
                and int(self._capture_staging_streak_by_unit.get(uid, 0) if uid else 0) >= 2
            ):
                forced_near_vp_pool = vp_relevant_attacks if vp_relevant_attacks else attacks
                forced_near_vp = self._best_attack(forced_near_vp_pool, state=state, unit=unit)
                if forced_near_vp is not None:
                    forced_near_vp.rl_capture_fallback_to_attack = True
                    forced_near_vp.rl_capture_fallback_reason = "forced_attack_near_vp_staging"
                    forced_near_vp.rl_capture_move_block_profile = move_reason or "objective_staging_move"
                    forced_near_vp.rl_capture_target_dist_before = dist_before
                    forced_near_vp.rl_capture_target_dist_after = dist_after
                    forced_near_vp.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(forced_near_vp, move_debug)
                    self._attach_vp_entry_debug(forced_near_vp, has_legal_stepin, False, default_block_reason or move_reason or "forced_attack_near_vp_staging")
                    forced_near_vp.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    return forced_near_vp, TacticalOption.ATTACK
            gated = None
            gated_score = float("-inf")
            gated_reason = ""
            for a in attacks:
                target = self._resolve_action_target(state, a)
                if target is None or not getattr(target, "alive", False):
                    continue
                adv = float(getattr(unit, "get_combat_advantage", lambda t: 0.0)(target))
                target_on_vp = self._is_target_on_enemy_or_neutral_vp(state, unit, target)
                target_threatens_owned_vp = self._is_target_on_owned_vp(state, unit, target)
                near_vp_pressure = nearest_vp_d is not None and nearest_vp_d <= 2 and adv >= -0.05
                target_near_uncaptured_vp = self._is_target_near_uncaptured_vp(state, unit, target, max_dist=1)
                support_lane_opening = (
                    unit_role == "SUPPORT"
                    and nearest_vp_d is not None
                    and 2 <= float(nearest_vp_d) <= 3
                    and target_near_uncaptured_vp
                    and adv >= -0.10
                )
                if not (target_on_vp or target_threatens_owned_vp or near_vp_pressure or support_lane_opening or adv >= 0.25):
                    continue
                score = adv
                if target_on_vp:
                    score += 1.0
                if target_threatens_owned_vp:
                    score += 0.8
                if near_vp_pressure:
                    score += 0.5
                if support_lane_opening:
                    score += 0.9
                if (
                    nearest_vp_d is not None
                    and float(nearest_vp_d) <= 3.0
                    and not target_on_vp
                    and not target_threatens_owned_vp
                    and not target_near_uncaptured_vp
                    and adv < 0.45
                ):
                    continue
                if score > gated_score:
                    gated_score = score
                    gated = a
                    if target_on_vp:
                        gated_reason = "attack_gate_vp_target"
                    elif target_threatens_owned_vp:
                        gated_reason = "attack_gate_defend_owned_vp"
                    elif near_vp_pressure:
                        gated_reason = "attack_gate_near_vp_pressure"
                    elif support_lane_opening:
                        gated_reason = "attack_gate_support_open_lane"
                    else:
                        gated_reason = "attack_gate_high_adv"
            if gated is not None:
                should_take_attack = move_reason in {"all_moves_increase_distance", "no_progress_move_available"}
                # Near VP, default to mobility unless attack is explicitly VP-relevant.
                if prefer_mobility_near_vp and gated_reason not in {
                    "attack_gate_vp_target",
                    "attack_gate_defend_owned_vp",
                    "attack_gate_support_open_lane",
                }:
                    should_take_attack = False
                # If we are stalled near VP for multiple consecutive decisions,
                # allow tactical attacks again to avoid zero-damage deadlocks.
                if (
                    uid
                    and move_reason == "objective_staging_move"
                    and nearest_vp_d is not None
                    and float(nearest_vp_d) <= 3.0
                    and int(self._capture_staging_streak_by_unit.get(uid, 0)) >= 2
                ):
                    should_take_attack = True
                if (
                    uid
                    and move_reason == "objective_staging_move"
                    and nearest_vp_d is not None
                    and nearest_vp_d <= 3
                    and int(self._capture_staging_streak_by_unit.get(uid, 0)) >= 3
                ):
                    should_take_attack = True
                if should_take_attack:
                    gated.rl_capture_fallback_to_attack = True
                    gated.rl_capture_fallback_reason = gated_reason
                    gated.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                    gated.rl_capture_target_dist_before = dist_before
                    gated.rl_capture_target_dist_after = dist_after
                    gated.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(gated, move_debug)
                    self._attach_vp_entry_debug(gated, has_legal_stepin, False, default_block_reason or move_reason or gated_reason)
                    gated.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    return gated, TacticalOption.ATTACK

        near_vp = nearest_vp_d is not None and float(nearest_vp_d) <= 3.0
        if move is not None and (
            move_reason == "objective_progress_move"
            or (move_reason == "objective_staging_move" and not near_vp)
        ):
            move.rl_capture_fallback_reason = move_reason
            move.rl_capture_move_block_profile = move_reason
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            self._attach_capture_progress_debug(move, move_debug)
            self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason)
            move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
            move.rl_vp_opening_attack_candidates_count = 0
            return move, TacticalOption.ADVANCE

        if attacks:
            relaxed_pool = []
            for a in attacks:
                target = self._resolve_action_target(state, a)
                if target is None or not getattr(target, "alive", False):
                    continue
                if (
                    self._is_target_on_enemy_or_neutral_vp(state, unit, target)
                    or self._is_target_on_owned_vp(state, unit, target)
                ):
                    relaxed_pool.append(a)
            best = self._best_attack(relaxed_pool, state=state, unit=unit) if relaxed_pool else None
            if best is not None:
                best.rl_capture_fallback_to_attack = True
                best.rl_capture_fallback_reason = "attack_gate_relaxed_fallback"
                best.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                best.rl_capture_target_dist_before = dist_before
                best.rl_capture_target_dist_after = dist_after
                self._attach_capture_progress_debug(best, move_debug)
                self._attach_vp_entry_debug(best, has_legal_stepin, False, default_block_reason or move_reason or "attack_gate_relaxed_fallback")
                best.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                best.rl_vp_opening_attack_candidates_count = int(len(relaxed_pool))
                return best, TacticalOption.ATTACK

        if move is not None:
            move.rl_capture_fallback_reason = "fallback_move_even_if_no_progress"
            move.rl_capture_move_block_profile = move_reason
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            self._attach_capture_progress_debug(move, move_debug)
            self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason or "fallback_move_even_if_no_progress")
            move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
            move.rl_vp_opening_attack_candidates_count = 0
            return move, TacticalOption.ADVANCE
        # Last-resort anti-passivity close to objectives:
        # if we are near uncaptured VP and capture logic cannot find progress,
        # try heuristic movement options before holding.
        if near_vp:
            for fallback_option, fallback_reason in (
                (TacticalOption.ADVANCE, "forced_near_vp_no_hold_advance"),
                (TacticalOption.FLANK, "forced_near_vp_no_hold_flank"),
            ):
                fallback_action = self.heuristic.choose_action(state, unit, fallback_option)
                if fallback_action is not None and not self._is_attack_action(fallback_action):
                    fallback_action.rl_capture_fallback_reason = fallback_reason
                    fallback_action.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                    fallback_action.rl_capture_target_dist_before = dist_before
                    fallback_action.rl_capture_target_dist_after = dist_after
                    self._attach_capture_progress_debug(fallback_action, move_debug)
                    self._attach_vp_entry_debug(
                        fallback_action,
                        has_legal_stepin,
                        False,
                        default_block_reason or move_reason or fallback_reason,
                    )
                    fallback_action.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    fallback_action.rl_vp_opening_attack_candidates_count = 0
                    return fallback_action, fallback_option
        hold = WaitAction(unit.unit_id)
        hold.rl_capture_fallback_reason = "no_move_no_attack_hold"
        hold.rl_capture_move_block_profile = move_reason or "no_movement_actions"
        self._attach_capture_progress_debug(hold, move_debug)
        self._attach_vp_entry_debug(hold, has_legal_stepin, False, default_block_reason or move_reason or "no_move_no_attack_hold")
        hold.rl_vp_nearest_uncaptured_dist = nearest_vp_d
        hold.rl_vp_opening_attack_candidates_count = 0
        return hold, TacticalOption.HOLD
