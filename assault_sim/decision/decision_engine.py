import copy

from assault_model.actions.status import WaitAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.map.hex_utils import safe_hex_distance

from assault_model.map.hex_coord import HexCoord


class DecisionEngine:
    def __init__(self):
        self._unit_selection_cache = {}

    # --------------------------------------------------
    # MAIN
    # --------------------------------------------------
    def compute_intent(self, env):
        state = env.game_state
        runtime = env.runtime
        active_side = runtime.active_side

        cache_key = (
            active_side,
            tuple(sorted(runtime.activated_units))
        )

        if cache_key in self._unit_selection_cache:
            return self._unit_selection_cache[cache_key]

        units = [
            u for u in state.units
            if u.side == active_side
            and u.alive
            and u.unit_id not in runtime.activated_units
        ]

        if not units:
            return None

        best_unit = None
        best_action = None
        best_score = float("-inf")

        # ✅ priorizar unidades sanas
        units = sorted(units, key=lambda u: getattr(u, "hp", 0), reverse=True)

        for unit in units:
            actions = self._get_unit_actions(env, unit)

            for action in actions:
                score = self.evaluate_action(env, action, active_side)

                if score > best_score:
                    best_score = score
                    best_unit = unit
                    best_action = action

        if best_unit and best_action:
            result = (best_unit, best_action)
            self._unit_selection_cache[cache_key] = result
            return result

        return None

    # --------------------------------------------------
    def clear_cache(self):
        self._unit_selection_cache.clear()

    # --------------------------------------------------
    def _get_unit_actions(self, env, unit):
        catalog = ActionCatalog(
            env.game_state,
            unit,
            terrain_config=env.game_state.game_map.terrain_config
        )
        return catalog.actions()

    # --------------------------------------------------
    # ✅ MAIN EVALUATION
    # --------------------------------------------------
    def evaluate_action(self, env, action, side):
        try:
            state = env.game_state

            base_score = self._evaluate_state_quality(state, side)
            combat_score = self._evaluate_expected_combat(action)
            progress_score = self._evaluate_movement_progress(env, action, side)
            action_bonus = self._action_bias(action)

            return base_score + combat_score + progress_score + action_bonus

        except Exception:
            return self._heuristic_score(action)

    # --------------------------------------------------
    # 🔥 MOVEMENT PROGRESS (FIX PRINCIPAL)
    # --------------------------------------------------
    def _evaluate_movement_progress(self, env, action, side):

        unit = getattr(action, "unit", None) or getattr(action, "actor", None)

        if unit is None or not getattr(unit, "position", None):
            return 0

        state = env.game_state

        enemies = [
            u for u in state.units
            if u.side != side and getattr(u, "alive", True)
        ]

        if not enemies:
            return 0

        try:
            closest = min(
                enemies,
                key=lambda e: safe_hex_distance(unit.position, e.position)
            )
        except Exception:
            return 0

        start_pos = unit.position

        target_pos = None
        target = getattr(action, "target", None)
        move_path = getattr(action, "move_path", None) or getattr(action, "path", None)

        # Prefer the authoritative destination from the action path.
        if move_path:
            try:
                end = move_path[-1]
                if end is not None and hasattr(end, "q") and hasattr(end, "r"):
                    target_pos = HexCoord(end.q, end.r)
            except Exception:
                target_pos = None

        if target_pos is None:
            if isinstance(target, HexCoord):
                target_pos = target
            elif hasattr(action, "q") and hasattr(action, "r"):
                target_pos = HexCoord(action.q, action.r)

        if target_pos is None:
            return 0

        d_before = safe_hex_distance(start_pos, closest.position)
        d_after = safe_hex_distance(target_pos, closest.position)

        score = 0

        # ✅ 🔥 FUERZA AVANCE (clave real)
        score += (d_before - d_after) * 12

        # ✅ 🔥 SI ESTÁ LEJOS → EMPUJAR FUERTE
        if d_before > 4:
            score += 10

        # ✅ penalizar huir
        if d_after > d_before:
            score -= 6

        # ✅ contacto cercano
        if d_after <= 2:
            score += 10

        # ✅ cohesión de grupo (más humano)
        near_friends = sum(
            1 for f in state.units
            if f.side == side
            and getattr(f, "alive", True)
            and f != unit
            and f.position
            and safe_hex_distance(target_pos, f.position) <= 2
        )

        if near_friends == 0:
            score -= 4

        return score

    # --------------------------------------------------
    def _evaluate_expected_combat(self, action):

        unit = getattr(action, "unit", None) or getattr(action, "actor", None) or getattr(action, "attacker", None)
        target = getattr(action, "target", None)

        if unit is None or target is None:
            return 0

        if not getattr(target, "alive", True):
            return 50

        score = 0

        dmg = unit.get_expected_damage(target) if hasattr(unit, "get_expected_damage") else 0
        adv = unit.get_combat_advantage(target) if hasattr(unit, "get_combat_advantage") else 0

        # ✅ menos miedo → más humano
        if dmg <= 0.05:
            return -15

        score += dmg * 40
        score += adv * 25

        hp = getattr(target, "hp", 5)

        if hp <= 1:
            score += 60

        if hp > 6 and dmg < 0.2:
            score -= 20

        if unit.position and target.position:
            dist = safe_hex_distance(unit.position, target.position)

            if dist <= 2:
                score += 5
            elif dist > 5:
                score -= 10

        return score

    # --------------------------------------------------
    def _action_bias(self, action):
        name = action.__class__.__name__.lower()
        score = 0

        if "attack" in name:
            score += 12

        if "assault" in name:
            score += 25

        if "move" in name:
            score += 2

        if "wait" in name:
            score -= 20

        return score

    # --------------------------------------------------
    def _evaluate_state_quality(self, state, side):

        vp_score = 0
        if hasattr(state, "vp_tracker") and hasattr(state.vp_tracker, "total_points"):
            vp_score = state.vp_tracker.total_points

        friendly_units = [
            u for u in state.units
            if u.side == side and getattr(u, "alive", True)
        ]

        enemy_units = [
            u for u in state.units
            if u.side != side and getattr(u, "alive", True)
        ]

        friendly_hp = sum(getattr(u, "hp", 0) for u in friendly_units)
        enemy_hp = sum(getattr(u, "hp", 0) for u in enemy_units)

        num_friendly = len(friendly_units)
        num_enemy = len(enemy_units)

        progress_score = 0

        vp_positions = getattr(state.game_map, "vp_positions", []) if hasattr(state, "game_map") else []

        if vp_positions:
            for u in friendly_units:
                if u.position:
                    try:
                        min_dist = min(
                            safe_hex_distance(u.position, HexCoord(vp[0], vp[1]))
                            for vp in vp_positions
                        )
                        progress_score -= min_dist
                    except:
                        pass

        score = 0

        score += vp_score * 120
        score += (friendly_hp - enemy_hp) * 4

        # ✅ equilibrio humano (antes 50 → demasiado agresivo)
        score += (num_friendly - num_enemy) * 25

        score += progress_score * 3

        return score

    # --------------------------------------------------
    def _heuristic_score(self, action):
        score = 0
        name = action.__class__.__name__.lower()

        if "attack" in name:
            score += 40
        if "assault" in name:
            score += 60
        if "move" in name:
            score += 15
        if "wait" in name:
            score -= 10

        return score
