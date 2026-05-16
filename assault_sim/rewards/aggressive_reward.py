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

        # 🔥 importante: lo vas a actualizar desde fuera
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

        # -------------------------------------------------
        # 🔥 PROGRESS
        # -------------------------------------------------
        progress = self.current_update / self.total_updates

        # -------------------------------------------------
        # 🥇 FASE 1 (0 → 0.3)
        # aprender supervivencia + daño básico
        # -------------------------------------------------
        if progress < 0.3:

            # daño
            reward += 0.1 * info.get("damage", 0)

            # kill fuerte
            if info.get("defender_killed"):
                reward += 1.0

            # morir penaliza fuerte
            if active and not active.alive:
                reward -= 1.0

        # -------------------------------------------------
        # 🥈 FASE 2 (0.3 → 0.6)
        # añade posición
        # -------------------------------------------------
        elif progress < 0.6:

            reward += self.combat.compute(
                action_name=action_name,
                info=info
            )

            reward += self.survival.compute(
                active=active,
                info=info
            )

            reward += 0.3 * self.position.compute(
                state=state,
                next_state=next_state,
                pre_dist=pre_dist,
                post_dist=post_dist
            )

        # -------------------------------------------------
        # 🥉 FASE 3 (0.6 → 1.0)
        # reward completo
        # -------------------------------------------------
        else:

            reward += self.combat.compute(
                action_name=action_name,
                info=info
            )

            reward += self.survival.compute(
                active=active,
                info=info
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
            reward -= 0.05 * min(self.wait_streak, 5)
        else:
            self.wait_streak = 0

        # -------------------------------------------------
        # COSTE TIEMPO
        # -------------------------------------------------
        reward -= 0.01

        # -------------------------------------------------
        # CLIP
        # -------------------------------------------------
        reward = max(min(reward, 5.0), -5.0)

        return reward
