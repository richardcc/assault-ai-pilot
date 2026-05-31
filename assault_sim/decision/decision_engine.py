import copy
from assault_model.actions.status import WaitAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.map.hex_utils import hex_distance
from assault_model.map.hex_coord import HexCoord
from assault_sim.strategy.formation_strategy import FormationStrategyEngine


class DecisionEngine:
    """
    Improved Decision Engine

    ✅ Preserves original structure
    ✅ Adds combat awareness
    ✅ Improves action scoring
    ✅ Keeps compatibility with PPO / HRL

    Returns INTENT only (no execution)
    """

    def __init__(self):
        self._unit_selection_cache = {}

    # --------------------------------------------------
    # MAIN ENTRY
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
            and u.unit_id not in runtime.activated_units
        ]

        if not units:
            return None

        best_unit = None
        best_action = None
        best_score = float("-inf")

        # 🔥 NUEVO: priorización ligera de unidades útiles
        units = sorted(
            units,
            key=lambda u: getattr(u, "hp", 0),
            reverse=True
        )

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
    # ✅ IMPROVED ACTION EVALUATION
    # --------------------------------------------------
    def evaluate_action(self, env, action, side):
        try:
            sandbox_env = copy.deepcopy(env)

            # Disable events
            if hasattr(sandbox_env, "event_bus"):
                sandbox_env.event_bus = None

            # snapshot before
            before_state = sandbox_env.game_state
            before_hp = {
                u.unit_id: getattr(u, "hp", 0)
                for u in before_state.units
            }

            sandbox_env.step(action)

            after_state = sandbox_env.game_state

            base_score = self._evaluate_state_quality(after_state, side)

            # 🔥 NUEVO: evaluación de combate directo
            combat_score = self._evaluate_combat_delta(
                before_state,
                after_state,
                before_hp,
                side
            )

            # 🔥 NUEVO: bonus contextual de acción
            action_bonus = self._action_bias(action)

            return base_score + combat_score + action_bonus

        except Exception:
            return self._heuristic_score(action)

    # --------------------------------------------------
    # ✅ NUEVO: COMBAT DELTA
    # --------------------------------------------------
    def _evaluate_combat_delta(self, before, after, hp_before, side):
        friendly_loss = 0
        enemy_loss = 0

        for u in after.units:
            before_hp = hp_before.get(u.unit_id, 0)
            after_hp = getattr(u, "hp", 0)

            delta = before_hp - after_hp
            if delta <= 0:
                continue

            if u.side == side:
                friendly_loss += delta
            else:
                enemy_loss += delta

        score = 0

        # 🔥 clave: premiar trades positivos
        score += enemy_loss * 25
        score -= friendly_loss * 30

        # 🔥 kill detection
        for u in after.units:
            if u.side != side and not getattr(u, "alive", True):
                score += 80
            if u.side == side and not getattr(u, "alive", True):
                score -= 80

        return score

    # --------------------------------------------------
    # ✅ NUEVO: ACTION BIAS
    # --------------------------------------------------
    def _action_bias(self, action):
        name = action.__class__.__name__.lower()

        score = 0

        if "attack" in name:
            score += 10  # leve incentivo a atacar bien

        if "assault" in name:
            score += 25  # más risky → más reward

        if "move" in name:
            score += 5

        if "wait" in name:
            score -= 25  # ❗ penaliza pasividad

        return score

    # --------------------------------------------------
    # STATE EVALUATION (MEJORADO)
    # --------------------------------------------------
    def _evaluate_state_quality(self, state, side):

        # ------------------------
        # VP
        # ------------------------
        vp_score = 0
        if hasattr(state, "vp_tracker") and hasattr(state.vp_tracker, "total_points"):
            vp_score = state.vp_tracker.total_points

        # ------------------------
        # Units
        # ------------------------
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

        friendly_dead = len([
            u for u in state.units
            if u.side == side and not getattr(u, "alive", True)
        ])

        enemy_dead = len([
            u for u in state.units
            if u.side != side and not getattr(u, "alive", True)
        ])

        # ------------------------
        # LOW HP PRESSURE
        # ------------------------
        low_enemy = sum(1 for u in enemy_units if getattr(u, "hp", 0) <= 1)
        low_friendly = sum(1 for u in friendly_units if getattr(u, "hp", 0) <= 1)

        # ------------------------
        # VP DISTANCE
        # ------------------------
        progress_score = 0
        vp_positions = []

        if hasattr(state, "game_map") and hasattr(state.game_map, "vp_positions"):
            vp_positions = state.game_map.vp_positions

        if vp_positions:
            for u in friendly_units:
                if getattr(u, "position", None):
                    try:
                        min_dist = min(
                            hex_distance(
                                u.position,
                                HexCoord(vp[0], vp[1])
                            )
                            for vp in vp_positions
                        )
                        progress_score -= min_dist
                    except Exception:
                        pass

        # ------------------------
        # FINAL SCORE
        # ------------------------
        score = 0

        # 🎯 VP (más importante ahora)
        score += vp_score * 120

        # 💥 combate
        score += (friendly_hp - enemy_hp) * 6
        score += (num_friendly - num_enemy) * 50

        # ☠ kills
        score += enemy_dead * 90
        score -= friendly_dead * 90

        # presión
        score += low_enemy * 30
        score -= low_friendly * 30

        # 🧭 posicionamiento
        score += progress_score * 3

        return score

    # --------------------------------------------------
    def _heuristic_score(self, action):
        score = 0
        name = action.__class__.__name__.lower()

        if "attack" in name:
            score += 50
        if "assault" in name:
            score += 70
        if "move" in name:
            score += 20
        if "wait" in name:
            score -= 20

        return score
