import copy

from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.assault import AssaultAction
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction
from assault_model.map.hex_utils import safe_hex_distance


class OptionExecutorCombatMixin:
    _MELEE_ADV_MIN = 0.35

    def _enemy_min_dist_for_pos(self, state, side, pos):
        try:
            enemies = self._enemy_positions_array(state, side)  # type: ignore[attr-defined]
            d = self._min_hex_distance_to_coords(pos, enemies)  # type: ignore[attr-defined]
            if d is not None:
                return d
        except Exception:
            pass
        enemy_units = [
            e for e in getattr(state, "units", [])
            if getattr(e, "alive", False)
            and getattr(e, "side", None) != side
            and getattr(e, "position", None) is not None
        ]
        if not enemy_units:
            return None
        return min(safe_hex_distance(pos, e.position) for e in enemy_units)

    def _attack_reposition_improves_fire_window(self, state, unit, action) -> bool:
        if state is None or unit is None or action is None:
            return False
        unit_pos = getattr(unit, "position", None)
        path = getattr(action, "path", None)
        if unit_pos is None or not path:
            return False
        end = path[-1]
        if end is None:
            return False
        before_enemy = self._enemy_min_dist_for_pos(state, getattr(unit, "side", None), unit_pos)
        after_enemy = self._enemy_min_dist_for_pos(state, getattr(unit, "side", None), end)
        if before_enemy is None or after_enemy is None:
            return False
        # Fire-window proxy: improves shortest enemy distance and reaches likely
        # next-turn firing geometry even without immediate legal shot now.
        return float(after_enemy) <= 3.0 and float(after_enemy) < float(before_enemy)

    def _attack_reposition_legal_followup_status(self, state, unit, action) -> tuple[bool, str]:
        if bool(getattr(self, "fast_reposition_followup_check", False)):
            # Fast proxy for train_lean: avoid deepcopy(state) and approximate follow-up
            # using geometric/contact signals already computed on current state.
            try:
                if self._attack_reposition_improves_fire_window(state, unit, action):
                    return True, "fast_proxy_fire_window"
                if self._attack_reposition_enables_contact_proxy(state, unit, action):
                    return True, "fast_proxy_contact"
            except Exception:
                pass
            return False, "fast_proxy_no_followup"
        if state is None or unit is None or action is None:
            return False, "invalid_inputs"
        path = getattr(action, "path", None)
        if not path:
            return False, "missing_path"
        end = path[-1]
        if end is None:
            return False, "missing_end_pos"
        uid = getattr(unit, "unit_id", None)
        if not uid:
            return False, "missing_unit_id"
        try:
            sim_state = copy.deepcopy(state)
        except Exception:
            return False, "deepcopy_failed"
        sim_unit = next((u for u in getattr(sim_state, "units", []) if getattr(u, "unit_id", None) == uid), None)
        if sim_unit is None:
            return False, "sim_unit_not_found"
        try:
            sim_unit.position = end
        except Exception:
            return False, "sim_position_set_failed"
        try:
            sim_actions = self._get_unit_actions(sim_state, sim_unit)
        except Exception:
            return False, "sim_actions_failed"
        if any(self._is_attack_action(a) for a in sim_actions):
            return True, "ok"
        return False, "no_attack_actions_after_move"

    def _attack_reposition_has_objective_progress(self, state, unit, action) -> bool:
        if state is None or unit is None or action is None:
            return False
        unit_pos = getattr(unit, "position", None)
        path = getattr(action, "path", None)
        if unit_pos is None or not path:
            return False
        end = path[-1]
        if end is None:
            return False
        try:
            ring_before = self._nearest_uncaptured_vp_ring_dist_from_pos(state, unit.side, unit_pos)  # type: ignore[attr-defined]
            ring_after = self._nearest_uncaptured_vp_ring_dist_from_pos(state, unit.side, end)  # type: ignore[attr-defined]
            if ring_before is not None and ring_after is not None and float(ring_after) < float(ring_before):
                return True
        except Exception:
            pass
        try:
            vp_before = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, unit_pos)  # type: ignore[attr-defined]
            vp_after = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, end)  # type: ignore[attr-defined]
            if vp_before is not None and vp_after is not None and float(vp_after) < float(vp_before):
                return True
        except Exception:
            pass
        return False

    def _attack_reposition_enables_contact_proxy(self, state, unit, action) -> bool:
        if state is None or unit is None or action is None:
            return False
        unit_pos = getattr(unit, "position", None)
        path = getattr(action, "path", None)
        if unit_pos is None or not path:
            return False
        end = path[-1]
        if end is None:
            return False
        before_enemy = self._enemy_min_dist_for_pos(state, getattr(unit, "side", None), unit_pos)
        after_enemy = self._enemy_min_dist_for_pos(state, getattr(unit, "side", None), end)
        if before_enemy is None or after_enemy is None:
            return False
        # One-turn contact proxy: step into likely next-turn fire geometry.
        return float(after_enemy) <= 2.0 and float(after_enemy) < float(before_enemy)

    def _enemy_pressure_at_pos_simple(self, state, side, pos, radius: int = 3) -> float:
        if state is None or pos is None:
            return 0.0
        pressure = 0.0
        for e in getattr(state, "units", []):
            if not getattr(e, "alive", False):
                continue
            if getattr(e, "side", None) == side:
                continue
            epos = getattr(e, "position", None)
            if epos is None:
                continue
            d = safe_hex_distance(pos, epos)
            if d is None or d > int(radius):
                continue
            pressure += 1.0 / max(1.0, float(d))
        return float(pressure)

    def _attack_reposition_improves_pressure(self, state, unit, action) -> bool:
        if state is None or unit is None:
            return False
        unit_pos = getattr(unit, "position", None)
        path = getattr(action, "path", None)
        if unit_pos is None or not path:
            return False
        end = path[-1]
        if end is None:
            return False

        target_hex = None
        try:
            target_hex = self._objective_target_hex(state, unit)  # type: ignore[attr-defined]
        except Exception:
            target_hex = None

        if target_hex is not None:
            before = safe_hex_distance(unit_pos, target_hex)
            after = safe_hex_distance(end, target_hex)
            if after < before:
                return True

        before_enemy = self._enemy_min_dist_for_pos(state, getattr(unit, "side", None), unit_pos)
        after_enemy = self._enemy_min_dist_for_pos(state, getattr(unit, "side", None), end)
        if before_enemy is None or after_enemy is None:
            try:
                terrain_gain = float(self._terrain_tactical_score(state, unit, end)) - float(
                    self._terrain_tactical_score(state, unit, unit_pos)
                )
                return terrain_gain >= 1.0
            except Exception:
                return False
        if after_enemy < before_enemy:
            return True

        # v6 micro-reposition signal: allow non-distance-improving moves only if
        # they clearly improve local survivability/positioning.
        try:
            terrain_gain = float(self._terrain_tactical_score(state, unit, end)) - float(
                self._terrain_tactical_score(state, unit, unit_pos)
            )
        except Exception:
            terrain_gain = 0.0
        before_pressure = self._enemy_pressure_at_pos_simple(state, getattr(unit, "side", None), unit_pos, radius=3)
        after_pressure = self._enemy_pressure_at_pos_simple(state, getattr(unit, "side", None), end, radius=3)
        pressure_delta = before_pressure - after_pressure
        return terrain_gain >= 1.5 or pressure_delta >= 0.35

    def _is_attack_action(self, action) -> bool:
        return isinstance(
            action,
            (
                AssaultAction,
                RangedDirectAttack,
                RangedIndirectAttack,
                MoveThenFireAction,
                FireThenMoveAction,
            ),
        )

    def _resolve_action_target(self, state, action):
        key = (
            "attack_target",
            self._action_catalog_cache_state_key,  # type: ignore[attr-defined]
            id(action),
            getattr(action, "target_id", None),
        )
        cached = self._target_cache.get(key)  # type: ignore[attr-defined]
        if cached is not None:
            return cached
        target = getattr(action, "target", None)
        if target is not None:
            self._target_cache[key] = target  # type: ignore[attr-defined]
            return target
        target_id = getattr(action, "target_id", None)
        if target_id:
            out = next(
                (u for u in getattr(state, "units", []) if getattr(u, "unit_id", None) == target_id),
                None,
            )
            self._target_cache[key] = out  # type: ignore[attr-defined]
            return out
        self._target_cache[key] = None  # type: ignore[attr-defined]
        return None

    def _execute_attack(self, state, unit, attack_mode, allow_move_fallback: bool = False):
        _actions, _moves, attacks = self._get_unit_actions_partitioned(state, unit)
        if not attacks:
            if allow_move_fallback:
                fallback = self._move_closer(state, unit)
                setattr(fallback, "rl_attack_fallback_to_move", True)
                setattr(fallback, "rl_attack_fallback_reason", "no_legal_attack_move_fallback")
                return fallback
            # Reposition instead of idling: preserve pressure without turning
            # ATTACK intent into unconditional ADVANCE drift.
            reposition = self._flank_move(state, unit)
            if reposition is None or isinstance(reposition, WaitAction):
                reposition = self._move_closer(state, unit, capture_strict=False)
            if reposition is not None and not isinstance(reposition, WaitAction):
                turn_now = int(getattr(state, "turn", 0))
                near_vp_ctx = False
                try:
                    d_vp = self._nearest_uncaptured_vp_dist(state, unit)  # type: ignore[attr-defined]
                    near_vp_ctx = d_vp is not None and float(d_vp) <= 3.0
                except Exception:
                    near_vp_ctx = False
                can_use_budget = True
                if hasattr(self, "_can_consume_attack_reposition_budget"):
                    can_use_budget = bool(
                        self._can_consume_attack_reposition_budget(
                            getattr(unit, "side", None),
                            turn_now,
                            near_vp=near_vp_ctx,
                        )
                    )
                improves_pressure = self._attack_reposition_improves_pressure(state, unit, reposition)
                improves_objective = self._attack_reposition_has_objective_progress(state, unit, reposition)
                enables_contact = self._attack_reposition_enables_contact_proxy(state, unit, reposition)
                improves_fire_window = self._attack_reposition_improves_fire_window(state, unit, reposition)
                enables_legal_followup, legal_followup_status = self._attack_reposition_legal_followup_status(
                    state, unit, reposition
                )
                if near_vp_ctx:
                    # v14: near-VP allows bounded fire-window setup when objective
                    # progress is present, even if no immediate legal follow-up exists.
                    accept_reposition = bool(
                        enables_legal_followup and (improves_objective or improves_pressure)
                    ) or bool(improves_objective and improves_fire_window)
                else:
                    accept_reposition = bool(
                        enables_legal_followup or improves_pressure or improves_objective or enables_contact
                    )
                if can_use_budget and accept_reposition:
                    if hasattr(self, "_consume_attack_reposition_budget"):
                        self._consume_attack_reposition_budget(
                            getattr(unit, "side", None),
                            turn_now,
                            near_vp=near_vp_ctx,
                        )
                    setattr(reposition, "rl_attack_fallback_to_move", True)
                    if enables_legal_followup:
                        setattr(reposition, "rl_attack_fallback_reason", "no_legal_attack_legal_followup_setup")
                    elif improves_objective and improves_fire_window:
                        setattr(reposition, "rl_attack_fallback_reason", "no_legal_attack_fire_window_setup")
                    elif improves_objective:
                        setattr(reposition, "rl_attack_fallback_reason", "no_legal_attack_objective_push")
                    elif enables_contact:
                        setattr(reposition, "rl_attack_fallback_reason", "no_legal_attack_contact_setup")
                    else:
                        setattr(reposition, "rl_attack_fallback_reason", "no_legal_attack_reposition")
                    return reposition
                if near_vp_ctx and can_use_budget:
                    objective_push = self._move_closer(state, unit, capture_strict=True)
                    objective_push_followup_ok = False
                    objective_push_followup_status = "not_checked"
                    objective_push_fire_window = False
                    if (
                        objective_push is not None
                        and not isinstance(objective_push, WaitAction)
                        and self._attack_reposition_has_objective_progress(state, unit, objective_push)
                    ):
                        objective_push_fire_window = self._attack_reposition_improves_fire_window(
                            state, unit, objective_push
                        )
                        (
                            objective_push_followup_ok,
                            objective_push_followup_status,
                        ) = self._attack_reposition_legal_followup_status(state, unit, objective_push)
                    if (
                        objective_push is not None
                        and not isinstance(objective_push, WaitAction)
                        and self._attack_reposition_has_objective_progress(state, unit, objective_push)
                        and (objective_push_followup_ok or objective_push_fire_window)
                    ):
                        if hasattr(self, "_consume_attack_reposition_budget"):
                            self._consume_attack_reposition_budget(
                                getattr(unit, "side", None),
                                turn_now,
                                near_vp=near_vp_ctx,
                            )
                        setattr(objective_push, "rl_attack_fallback_to_move", True)
                        if objective_push_followup_ok:
                            setattr(objective_push, "rl_attack_fallback_reason", "no_legal_attack_forced_objective_push")
                        else:
                            setattr(objective_push, "rl_attack_fallback_reason", "no_legal_attack_forced_fire_window_push")
                        return objective_push
                    hold = WaitAction(unit.unit_id)
                    setattr(hold, "rl_attack_fallback_to_move", False)
                    if objective_push is None or isinstance(objective_push, WaitAction):
                        diag_suffix = "objective_push_unavailable"
                    elif not self._attack_reposition_has_objective_progress(state, unit, objective_push):
                        diag_suffix = "objective_push_no_progress"
                    else:
                        diag_suffix = f"objective_push_followup_{objective_push_followup_status}"
                    if (
                        not enables_legal_followup
                        and legal_followup_status
                        and legal_followup_status != "ok"
                    ):
                        diag_suffix = f"reposition_followup_{legal_followup_status}"
                    setattr(
                        hold,
                        "rl_attack_fallback_reason",
                        f"no_legal_attack_no_followup_near_vp:{diag_suffix}",
                    )
                    return hold
            hold = WaitAction(unit.unit_id)
            setattr(hold, "rl_attack_fallback_to_move", False)
            setattr(hold, "rl_attack_fallback_reason", "no_legal_attack_hold_no_progress")
            return hold
        best = self._best_attack(attacks, state=state, unit=unit)
        chosen = best if best else attacks[0]
        setattr(chosen, "rl_attack_fallback_to_move", False)
        setattr(chosen, "rl_attack_fallback_reason", "")
        return chosen

    def _has_immediate_attack(self, state, unit) -> bool:
        _actions, _moves, attacks = self._get_unit_actions_partitioned(state, unit)
        return bool(attacks)

    def _best_attack(self, attacks, state=None, unit=None):
        best = None
        best_score = float("-inf")
        for a in attacks:
            target = self._resolve_action_target(state, a)
            if target is None or not target.alive:
                continue

            unit_obj = (
                getattr(a, "unit", None)
                or getattr(a, "actor", None)
                or getattr(a, "attacker", None)
                or unit
            )
            if unit_obj is None:
                continue

            adv = unit_obj.get_combat_advantage(target)
            exp_dmg = getattr(unit_obj, "get_expected_damage", lambda t: 0.0)(target)
            hp = getattr(target, "hp", 10)
            is_move_then_fire = isinstance(a, MoveThenFireAction)
            is_fire_then_move = isinstance(a, FireThenMoveAction)
            is_assault = isinstance(a, AssaultAction)

            # Conservative melee gate: only engage close combat on clearly favorable
            # combat advantage so we avoid suicidal hex-entry charges.
            if is_assault and adv < float(self._MELEE_ADV_MIN):
                continue

            if (is_move_then_fire or is_fire_then_move) and exp_dmg <= 0.02 and hp > 2:
                continue
            if is_move_then_fire or is_fire_then_move:
                target_on_vp = (
                    state is not None
                    and unit_obj is not None
                    and self._is_target_on_enemy_or_neutral_vp(state, unit_obj, target)
                )
                if not target_on_vp:
                    if adv < 0.25:
                        continue
                    if exp_dmg < 0.15:
                        continue

            if self.avoid_bad_trades:
                if adv < -0.3:
                    continue
                if adv < self.adv_threshold:
                    continue
                if adv < 0.0 and hp > 6:
                    continue
                if exp_dmg <= 0.05 and hp > 3:
                    continue

            score = 0
            score += adv * 30
            score += (10 - hp) * 3
            if hp <= 1:
                score += 60
            score -= hp * 2
            score += 5

            if is_move_then_fire:
                score += 1
            elif is_fire_then_move:
                score += 0.5
            elif is_assault:
                score += 20

            if state is not None and unit_obj is not None and self._is_target_on_enemy_or_neutral_vp(state, unit_obj, target):
                score += 35

            if hasattr(unit_obj, "position") and hasattr(target, "position"):
                dist = safe_hex_distance(unit_obj.position, target.position)
                if dist <= 2:
                    score += 3
                elif dist > 6:
                    score -= 5

            if state is not None and (is_move_then_fire or is_fire_then_move):
                move_path = getattr(a, "move_path", None) or []
                if move_path:
                    end = move_path[-1]
                    score += 0.2 * self._terrain_tactical_score(state, unit_obj, end)

            if score > best_score:
                best_score = score
                best = a
                setattr(best, "rl_attack_expected_damage", float(exp_dmg or 0.0))

        if best is not None:
            return best
        return attacks[0] if attacks else WaitAction("SYSTEM")


__all__ = ["OptionExecutorCombatMixin"]
