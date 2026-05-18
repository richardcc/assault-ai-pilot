from .base_reward import BaseReward


class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None):
        super().__init__(rl_side)
        self.rl_side = rl_side

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

        info = info or {}
        reward = 0.0

        # -------------------------------------------------
        # ✅ DAMAGE DEALT (principal señal positiva)
        # -------------------------------------------------
        damage = info.get("damage", 0)
        reward += 0.4 * damage

        if damage > 0:
            reward += 0.03

        # -------------------------------------------------
        # ✅ DAMAGE TAKEN (🔥 NUEVO — CLAVE)
        # -------------------------------------------------
        damage_taken = info.get("damage_taken", 0)
        reward -= 0.3 * damage_taken

        # -------------------------------------------------
        # ACTION TYPE
        # -------------------------------------------------
        action_name = action.__class__.__name__ if action else ""

        # -------------------------------------------------
        # ✅ PENALIZAR SOLO DIRECT VACÍO
        # -------------------------------------------------
        if damage == 0 and "RangedDirect" in action_name:
            reward -= 0.005

        # -------------------------------------------------
        # ✅ BONUS INDIRECT
        # -------------------------------------------------
        if "Indirect" in action_name and damage > 0:
            reward += 0.3

        # -------------------------------------------------
        # ✅ BONUS MELEE
        # -------------------------------------------------
        if "Close" in action_name and info.get("defender_killed"):
            reward += 1.0

        # -------------------------------------------------
        # ✅ MICRO BONUS A ATACAR (SOLO SI FUNCIONA)
        # -------------------------------------------------
        if "Attack" in action_name and damage > 0:
            reward += 0.01

        # -------------------------------------------------
        # ✅ KILL
        # -------------------------------------------------
        if info.get("defender_killed"):
            reward += 3.0

        # -------------------------------------------------
        # ✅ DEATH (ligero castigo)
        # -------------------------------------------------
        if active and not active.alive:
            reward -= 3.0

        # -------------------------------------------------
        # ✅ VP diferencial
        # -------------------------------------------------
        try:
            if hasattr(state, "vp_tracker") and hasattr(next_state, "vp_tracker"):
                prev_vp = state.vp_tracker.score(self.rl_side)
                new_vp = next_state.vp_tracker.score(self.rl_side)

                reward += (new_vp - prev_vp) * 1.0
        except Exception:
            pass

        # -------------------------------------------------
        # ✅ ENDGAME (CLAVE)
        # -------------------------------------------------
        if getattr(next_state, "done", False):
            if getattr(next_state, "winner", None) == self.rl_side:
                reward += 10.0
            elif getattr(next_state, "winner", None) is not None:
                reward -= 10.0

        # -------------------------------------------------
        # ✅ TIME COST
        # -------------------------------------------------
        reward -= 0.01

        # -------------------------------------------------
        # ✅ CLIP
        # -------------------------------------------------
        reward = max(min(reward, 10.0), -10.0)

        return reward