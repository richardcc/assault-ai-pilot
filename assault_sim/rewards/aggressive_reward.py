from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import hex_distance
from .base_reward import BaseReward


class AggressiveReward(BaseReward):

    def compute(
        self,
        *,
        state,
        next_state,
        action,
        active,
        info,
        pre_dist,
        post_dist
    ) -> float:

        reward = 0.0

        # -------------------------------------------------
        # ✅ 1. VP (DOMINANTE 🔥)
        # -------------------------------------------------
        current_vp = next_state.vp_tracker.total_points if next_state.vp_tracker else 0
        reward += 10.0 * (current_vp - self.prev_vp)
        self.prev_vp = current_vp

        # -------------------------------------------------
        # ✅ 2. OCUPAR + MANTENER VP (CRÍTICO)
        # -------------------------------------------------
        if active is not None and next_state.vp_tracker:
            for vp in next_state.vp_tracker.conditions.points:
                if active.position == vp.hex_coords:
                    reward += 2.0   # ocupar
                    reward += 1.0   # mantener (cada turno)

        # -------------------------------------------------
        # ✅ 3. ATAQUE (REDUCIDO para no competir con VP)
        # -------------------------------------------------
        action_name = action.__class__.__name__ if action else ""
        is_attack = "Ranged" in action_name or "Close" in action_name

        if is_attack:
            reward += 0.3

        info = info or {}

        dmg = info.get("damage", 0)
        killed = info.get("defender_killed", False)

        reward += 0.25 * dmg

        if killed:
            reward += 1.5

        # -------------------------------------------------
        # ✅ 4. MOVIMIENTO HACIA ENEMIGO
        # -------------------------------------------------
        if pre_dist is not None and post_dist is not None:
            delta = pre_dist - post_dist
            reward += 0.5 * delta

            if delta < 0:
                reward -= 0.5

        # -------------------------------------------------
        # ✅ 5. MOVIMIENTO HACIA VP (🔥 ESTRATEGIA REAL)
        # -------------------------------------------------
        if active is not None and next_state.vp_tracker:

            vp_points = next_state.vp_tracker.conditions.points

            if vp_points:

                # distancia antes
                pre_vp_dist = min(
                    hex_distance(active.position, vp.hex_coords)
                    for vp in vp_points
                )

                # buscar unidad en next_state
                next_active = next(
                    (u for u in next_state.units if u.unit_id == active.unit_id),
                    None
                )

                if next_active:
                    post_vp_dist = min(
                        hex_distance(next_active.position, vp.hex_coords)
                        for vp in vp_points
                    )

                    delta_vp = pre_vp_dist - post_vp_dist
                    reward += 0.5 * delta_vp

        # -------------------------------------------------
        # ✅ 6. WAIT (castigo fuerte)
        # -------------------------------------------------
        if isinstance(action, WaitAction):
            reward -= 0.5

        if getattr(self, "last_action_was_wait", False) and isinstance(action, WaitAction):
            reward -= 0.2

        self.last_action_was_wait = isinstance(action, WaitAction)

        # -------------------------------------------------
        # ✅ 7. CONSISTENCIA MOVIMIENTO
        # -------------------------------------------------
        if action_name == "MoveAction" and pre_dist is not None and post_dist is not None:
            if post_dist < pre_dist:
                reward += 0.2

        # -------------------------------------------------
        # ✅ 8. COSTE DE TIEMPO
        # -------------------------------------------------
        reward -= 0.02

        # -------------------------------------------------
        # ✅ 9. CLIPPING (AL FINAL SIEMPRE)
        # -------------------------------------------------
        reward = max(min(reward, 5.0), -5.0)

        return reward