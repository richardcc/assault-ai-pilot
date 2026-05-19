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
        # ✅ DAMAGE DEALT (signal principal)
        # -------------------------------------------------
        damage = info.get("damage", 0)
        reward += 0.7 * damage   # 🔥 ligeramente más fuerte

        if damage > 0:
            reward += 0.15   # 🔥 refuerzo claro

        # -------------------------------------------------
        # ✅ DAMAGE TAKEN (reducido → menos miedo)
        # -------------------------------------------------
        damage_taken = info.get("damage_taken", 0)
        reward -= 0.15 * damage_taken

        # -------------------------------------------------
        # ACTION TYPE
        # -------------------------------------------------
        action_name = action.__class__.__name__ if action else ""
        action_upper = action_name.upper()

        # -------------------------------------------------
        # ✅ PENALIZAR ATAQUE FALLIDO (muy ligero)
        # -------------------------------------------------
        if damage == 0 and "RANGEDDIRECT" in action_upper:
            reward -= 0.01

        # -------------------------------------------------
        # ✅ BONUS INDIRECT
        # -------------------------------------------------
        if "INDIRECT" in action_upper and damage > 0:
            reward += 0.3

        # -------------------------------------------------
        # ✅ BONUS MELEE
        # -------------------------------------------------
        if "CLOSE" in action_upper and info.get("defender_killed"):
            reward += 1.0

        # -------------------------------------------------
        # ✅ INCENTIVAR ATAQUE (CLAVE)
        # -------------------------------------------------
        if "ATTACK" in action_upper:
            reward += 0.3   # 🔥 antes era demasiado bajo

        if "ATTACK" in action_upper and damage > 0:
            reward += 0.2   # 🔥 refuerzo doble

        # -------------------------------------------------
        # ✅ KILL (objetivo principal)
        # -------------------------------------------------
        if info.get("defender_killed"):
            reward += 4.0   # 🔥 más fuerte → evita pasividad

        # -------------------------------------------------
        # ✅ DEATH (penaliza pero no bloquea)
        # -------------------------------------------------
        if active and not active.alive:
            reward -= 2.5

        # -------------------------------------------------
        # ✅ PRESIÓN HACIA COMBATE
        # -------------------------------------------------
        if pre_dist is not None and post_dist is not None:

            if post_dist < pre_dist:
                reward += 0.06

            if post_dist > pre_dist:
                reward -= 0.01

            # 🔥 combate cercano incentivado
            if post_dist <= 2:
                reward += 0.05

        # -------------------------------------------------
        # ✅ EVITAR SPAM DE FLANK
        # -------------------------------------------------
        if "FLANK" in action_upper:
            reward -= 0.005

        # -------------------------------------------------
        # ✅ PENALIZAR HOLD
        # -------------------------------------------------
        if "HOLD" in action_upper:
            reward -= 0.08

        # -------------------------------------------------
        # ✅ PENALIZAR RETREAT (🔥 CRÍTICO)
        # -------------------------------------------------
        if "RETREAT" in action_upper:
            reward -= 0.05   # 🔥 evita colapso sin prohibirlo

        # -------------------------------------------------
        # ✅ VP diferencial
        # -------------------------------------------------
        try:
            if hasattr(state, "vp_tracker") and hasattr(next_state, "vp_tracker"):
                prev_vp = state.vp_tracker.score(self.rl_side)
                new_vp = next_state.vp_tracker.score(self.rl_side)
                reward += (new_vp - prev_vp) * 1.5
        except Exception:
            pass

        # -------------------------------------------------
        # ✅ ENDGAME
        # -------------------------------------------------
        if getattr(next_state, "done", False):
            if getattr(next_state, "winner", None) == self.rl_side:
                reward += 12.0
            elif getattr(next_state, "winner", None) is not None:
                reward -= 10.0

        # -------------------------------------------------
        # ✅ TIME COST (anti-camping)
        # -------------------------------------------------
        reward -= 0.02   # 🔥 ligero ajuste

        # -------------------------------------------------
        # ✅ CLIP
        # -------------------------------------------------
        reward = max(min(reward, 10.0), -10.0)

        return reward