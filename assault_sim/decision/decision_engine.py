import copy
from assault_model.actions.status import WaitAction
from assault_model.actions.action_catalog import ActionCatalog


class DecisionEngine:
    """
    Decision engine using:
    - ActionCatalog (action generation)
    - Environment simulation (lookahead)
    - Heuristic state evaluation (NO RL dependency)

    Returns INTENT only (no execution)
    """

    def __init__(self):
        # ✅ Cache to avoid recomputing same state decisions
        self._unit_selection_cache = {}

    # --------------------------------------------------
    # ✅ MAIN ENTRY WITH CACHE
    # --------------------------------------------------
    def compute_intent(self, env):
        state = env.game_state
        runtime = env.runtime
        active_side = runtime.active_side

        cache_key = (
            active_side,
            tuple(sorted(runtime.activated_units))
        )

        # ✅ CACHE HIT
        if cache_key in self._unit_selection_cache:
            return self._unit_selection_cache[cache_key]

        # 1. Available units
        units = [
            u for u in state.units
            if u.side == active_side
            and u.unit_id not in runtime.activated_units
        ]

        if not units:
            return None

        best_unit = None
        best_action = None
        best_score = -999999

        # 2. Evaluate all unit-action pairs
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
    # ✅ CLEAR CACHE
    # --------------------------------------------------
    def clear_cache(self):
        self._unit_selection_cache.clear()

    # --------------------------------------------------
    # ✅ ACTION GENERATION
    # --------------------------------------------------
    def _get_unit_actions(self, env, unit):
        catalog = ActionCatalog(
            env.game_state,
            unit,
            terrain_config=env.game_state.game_map.terrain_config
        )
        return catalog.actions()

    # --------------------------------------------------
    # ✅ EVALUATION (PURE, NO RL)
    # --------------------------------------------------
    def evaluate_action(self, env, action, side):
        """
        Simulates action outcome and evaluates resulting state.
        """

        try:
            # ✅ simulate action
            sandbox_env = copy.deepcopy(env)

            # Disable event emission (performance)
            if hasattr(sandbox_env, "event_bus"):
                sandbox_env.event_bus = None

            sandbox_env.step(action)

            # ✅ evaluate resulting state
            return self._evaluate_state_quality(
                sandbox_env.game_state,
                side
            )

        except Exception:
            return self._heuristic_score(action)

    # --------------------------------------------------
    # ✅ STATE EVALUATION (KEY FUNCTION)
    # --------------------------------------------------
    def _evaluate_state_quality(self, state, side):

        # ----------------------------------------
        # ✅ Victory Points
        # ----------------------------------------
        vp_score = 0
        if hasattr(state, "vp_tracker") and hasattr(state.vp_tracker, "total_points"):
            vp_score = state.vp_tracker.total_points

        # ----------------------------------------
        # ✅ Units split
        # ----------------------------------------
        friendly_units = [
            u for u in state.units
            if u.side == side and getattr(u, "alive", True)
        ]

        enemy_units = [
            u for u in state.units
            if u.side != side and getattr(u, "alive", True)
        ]

        # ----------------------------------------
        # ✅ HP
        # ----------------------------------------
        friendly_hp = sum(getattr(u, "hp", 0) for u in friendly_units)
        enemy_hp = sum(getattr(u, "hp", 0) for u in enemy_units)

        # ----------------------------------------
        # ✅ Unit counts
        # ----------------------------------------
        num_friendly = len(friendly_units)
        num_enemy = len(enemy_units)

        # ----------------------------------------
        # ✅ Dead units
        # ----------------------------------------
        friendly_dead = len([
            u for u in state.units
            if u.side == side and not getattr(u, "alive", True)
        ])

        enemy_dead = len([
            u for u in state.units
            if u.side != side and not getattr(u, "alive", True)
        ])

        # ----------------------------------------
        # ✅ Low HP units (critical state)
        # ----------------------------------------
        low_enemy = sum(
            1 for u in enemy_units if getattr(u, "hp", 0) <= 1
        )

        low_friendly = sum(
            1 for u in friendly_units if getattr(u, "hp", 0) <= 1
        )

        # ----------------------------------------
        # ✅ Distance to VP (progress signal)
        # ----------------------------------------
        def distance(a, b):
            return abs(a.q - b.q) + abs(a.r - b.r)

        progress_score = 0
        vp_positions = []

        if (
            hasattr(state, "game_map") and
            hasattr(state.game_map, "vp_positions")
        ):
            vp_positions = state.game_map.vp_positions

        if vp_positions:
            for u in friendly_units:
                if hasattr(u, "position"):
                    min_dist = min(
                        distance(u.position, vp)
                        for vp in vp_positions
                    )
                    progress_score -= min_dist  # más cerca = mejor

        # ----------------------------------------
        # ✅ FINAL SCORE
        # ----------------------------------------
        score = 0

        # 🎯 Objetivo de partida
        score += vp_score * 100

        # ⚔️ Combate
        score += (friendly_hp - enemy_hp) * 5
        score += (num_friendly - num_enemy) * 40

        # 💀 Eliminaciones
        score += enemy_dead * 80
        score -= friendly_dead * 80

        # 🔥 Estado crítico (setup de kills)
        score += low_enemy * 25
        score -= low_friendly * 25

        # 🗺️ Progreso estratégico
        score += progress_score * 2

        return score   

    # --------------------------------------------------
    # ✅ FALLBACK (IF SIMULATION FAILS)
    # --------------------------------------------------
    def _heuristic_score(self, action):
        score = 0
        action_type = action.__class__.__name__.lower()

        if "attack" in action_type:
            score += 50
        if "assault" in action_type:
            score += 70
        if "move" in action_type:
            score += 20
        if "wait" in action_type:
            score -= 10

        return score