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
        # DAMAGE (más incentivo a combatir)
        # -------------------------------------------------
        damage = info.get("damage", 0)
        reward += 0.4 * damage   # 🔥 antes 0.3

        # pequeño boost (reducido)
        if damage > 0:
            reward += 0.03       # 🔥 antes 0.05

        action_name = action.__class__.__name__ if action else ""

        # -------------------------------------------------
        # PENALIZAR SOLO DIRECT VACÍO (mucho más suave)
        # -------------------------------------------------
        if damage == 0 and "RangedDirect" in action_name:
            reward -= 0.005      # 🔥 antes 0.02

        # -------------------------------------------------
        # BONUS INDIRECT (mantener)
        # -------------------------------------------------
        if "Indirect" in action_name and damage > 0:
            reward += 0.3

        # -------------------------------------------------
        # BONUS MELEE
        # -------------------------------------------------
        if "Close" in action_name and info.get("defender_killed"):
            reward += 1.0

        # -------------------------------------------------
        # MICRO BONUS A ATACAR (anti-colapso)
        # -------------------------------------------------
        if "Attack" in action_name:
            reward += 0.01

        # -------------------------------------------------
        # KILL
        # -------------------------------------------------
        if info.get("defender_killed"):
            reward += 3.0

        # -------------------------------------------------
        # DEATH (reducido para evitar miedo excesivo)
        # -------------------------------------------------
        if active and not active.alive:
            reward -= 3.0    # 🔥 antes 4.0

        # -------------------------------------------------
        # VP diferencial
        # -------------------------------------------------
        try:
            if hasattr(state, "vp_tracker") and hasattr(next_state, "vp_tracker"):
                prev_vp = state.vp_tracker.score(self.rl_side)
                new_vp = next_state.vp_tracker.score(self.rl_side)

                reward += (new_vp - prev_vp) * 1.0
        except Exception:
            pass

        # -------------------------------------------------
        # ENDGAME
        # -------------------------------------------------
        if getattr(next_state, "done", False):
            if getattr(next_state, "winner", None) == self.rl_side:
                reward += 10.0
            elif getattr(next_state, "winner", None) is not None:
                reward -= 10.0

        # -------------------------------------------------
        # TIME COST
        # -------------------------------------------------
        reward -= 0.01

        # -------------------------------------------------
        # CLIP
        # -------------------------------------------------
        reward = max(min(reward, 10.0), -10.0)

        return reward