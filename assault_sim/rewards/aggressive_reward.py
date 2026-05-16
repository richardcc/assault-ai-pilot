from .base_reward import BaseReward

from .components.combat_reward import CombatReward
from .components.survival_reward import SurvivalReward
from .components.positioning_reward import PositioningReward
from .components.vp_reward import VPReward

class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None):
        super().__init__(rl_side)

        self.rl_side = rl_side

        self.combat = CombatReward()
        self.survival = SurvivalReward()
        self.position = PositioningReward()
        self.vp = VPReward()

        self.wait_streak = 0

        self.current_update = 0
        self.total_updates = 4000

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

        action_name = action.__class__.__name__ if action else ""

        progress = self.current_update / self.total_updates

        # -------------------------------------------------
        # 🥇 FASE 1 (0 → 0.3)
        # ✅ introducir indirect DESDE EL INICIO
        # -------------------------------------------------
        if progress < 0.3:

            reward += 0.2 * info.get("damage", 0)

            if info.get("defender_killed"):
                reward += 2.0

            if active and not active.alive:
                reward -= 2.0

            # ✅ 🔥 CLAVE: indirect existe desde fase 1
            if "Indirect" in action_name:
                reward += 0.5

        # -------------------------------------------------
        # 🥈 FASE 2 (0.3 → 0.6)
        # ✅ más peso a posición
        # -------------------------------------------------
        elif progress < 0.6:

            reward += self.combat.compute(
                action_name=action_name,
                info=info
            )

            reward += self.survival.compute(
                active=active,
                info=info,
                action_name=action_name
            )

            # ✅ subir peso de posición
            reward += 0.5 * self.position.compute(
                state=state,
                next_state=next_state,
                pre_dist=pre_dist,
                post_dist=post_dist
            )

            # ✅ VP empieza antes
            reward += 0.3 * self.vp.compute(
                next_state=next_state,
                active=active
            )

        # -------------------------------------------------
        # 🥉 FASE 3 (0.6 → 1.0)
        # ✅ completo balanceado
        # -------------------------------------------------
        else:

            reward += self.combat.compute(
                action_name=action_name,
                info=info
            )

            reward += self.survival.compute(
                active=active,
                info=info,
                action_name=action_name
            )

            reward += self.position.compute(
                state=state,
                next_state=next_state,
                pre_dist=pre_dist,
                post_dist=post_dist
            )

            reward += self.vp.compute(
                next_state=next_state,
                active=active
            )

        # -------------------------------------------------
        # WAIT STREAK
        # -------------------------------------------------
        if "Wait" in action_name:
            self.wait_streak += 1
            reward -= 0.03 * min(self.wait_streak, 5)
        else:
            self.wait_streak = 0

        # -------------------------------------------------
        # COSTE TIEMPO
        # -------------------------------------------------
        reward -= 0.005

        # -------------------------------------------------
        # CLIP
        # -------------------------------------------------
        reward = max(min(reward, 5.0), -5.0)

        return reward
