from .base_reward import BaseReward
from assault_model.actions.status import WaitAction


class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None):
        super().__init__(rl_side)
        self.rl_side = rl_side

        # anti-spam
        self.last_action = None

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
        # ✅ DATOS
        # -------------------------------------------------
        damage = info.get("rl_damage", 0)
        damage_taken = info.get("enemy_damage", 0)
        killed = info.get("rl_kills", 0) > 0

        action_class = info.get("action_class", "")
        action_upper = action_class.upper()

        # ✅ 🔥 L2 REAL (CRÍTICO)
        l2 = info.get("l2_option", "")

        is_attack = "ATTACK" in action_upper

        # -------------------------------------------------
        # ✅ DAMAGE
        # -------------------------------------------------
        reward += 1.4 * damage

        if damage > 0:
            reward += 0.25

        # -------------------------------------------------
        # ✅ DAMAGE TAKEN
        # -------------------------------------------------
        reward -= 0.2 * damage_taken

        # -------------------------------------------------
        # ✅ ATAQUE BASE
        # -------------------------------------------------
        if is_attack:
            reward += 0.6

        if is_attack and damage > 0:
            reward += 1.0

        if is_attack and damage == 0:
            reward -= 0.01

        # -------------------------------------------------
        # ✅ TIPO DE ATAQUE
        # -------------------------------------------------
        if "ASSAULT" in action_upper:
            reward += 1.2

        elif "CLOSE" in action_upper:
            reward += 0.6

        elif "RANGED" in action_upper:
            reward += 0.3

        # anti-spam ranged
        if "RANGEDDIRECTATTACK" in action_upper:
            reward -= 0.2

        # -------------------------------------------------
        # ✅ ATAQUE CERCA
        # -------------------------------------------------
        if is_attack and pre_dist is not None and pre_dist <= 3:
            reward += 0.8

        # -------------------------------------------------
        # ✅ KILL
        # -------------------------------------------------
        if killed:
            reward += 6.0

        # -------------------------------------------------
        # ✅ MUERTE PROPIA
        # -------------------------------------------------
        if active and not active.alive:
            reward -= 3.0

        # -------------------------------------------------
        # ✅ MOVIMIENTO
        # -------------------------------------------------
        if pre_dist is not None and post_dist is not None:

            if post_dist < pre_dist:
                reward += 0.05

            if post_dist > pre_dist:
                reward -= 0.02

            if post_dist <= 2:
                reward += 0.1

        # -------------------------------------------------
        # ✅ NO ATACAR CERCA
        # -------------------------------------------------
        if not is_attack and pre_dist is not None and pre_dist <= 3:
            reward -= 0.4

        # -------------------------------------------------
        # ✅ INACTIVIDAD
        # -------------------------------------------------
        if damage == 0 and not is_attack:
            reward -= 0.08

        # -------------------------------------------------
        # ✅ WAIT
        # -------------------------------------------------
        if isinstance(action, WaitAction):
            reward -= 0.2

        # -------------------------------------------------
        # ✅ RETREAT
        # -------------------------------------------------
        if l2 == "RETREAT":
            reward -= 0.08

        # -------------------------------------------------
        # ✅ 🔥 FLANK (L2 REAL)
        # -------------------------------------------------
        if l2 == "FLANK":
            reward -= 0.25

            if pre_dist is not None and pre_dist <= 4:
                reward -= 0.6

        # -------------------------------------------------
        # ✅ 🔥 INCENTIVAR ATTACK (L2)
        # -------------------------------------------------
        if l2 == "ATTACK":
            reward += 0.6

        # -------------------------------------------------
        # ✅ 🔥 INCENTIVAR ADVANCE
        # -------------------------------------------------
        if l2 == "ADVANCE":
            reward += 0.2

        # -------------------------------------------------
        # ✅ ANTI-SPAM
        # -------------------------------------------------
        if self.last_action is not None and self.last_action == action_class:
            reward -= 0.1

        self.last_action = action_class

        # -------------------------------------------------
        # ✅ VP
        # -------------------------------------------------
        if hasattr(state, "vp_tracker") and state.vp_tracker:
            if hasattr(next_state, "vp_tracker") and next_state.vp_tracker:

                prev_vp = state.vp_tracker.score.get(self.rl_side, 0)
                new_vp = next_state.vp_tracker.score.get(self.rl_side, 0)

                delta_vp = new_vp - prev_vp

                if delta_vp != 0:
                    reward += delta_vp * 1.3

        # -------------------------------------------------
        # ✅ ENDGAME
        # -------------------------------------------------
        if getattr(next_state, "done", False):
            winner = getattr(next_state, "winner", None)

            if winner == self.rl_side:
                reward += 6.0
            elif winner is not None:
                reward -= 6.0

        # -------------------------------------------------
        # ✅ COSTE TEMPORAL
        # -------------------------------------------------
        reward -= 0.03

        # -------------------------------------------------
        # ✅ CLIP
        # -------------------------------------------------
        reward = max(min(reward, 10.0), -10.0)

        return reward