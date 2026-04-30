"""
Reward: VP + Tempo + Casualties (Scenario-aligned)

Scenario: "Mettete i piedi per terra!" (Campaign 1.0)

Design principles:
- VP capture is the primary objective
- Early tempo matters (push in turns 1–3)
- Casualties matter, but are acceptable if ground is gained
- Pure passivity is penalized indirectly via tempo/VP rules
"""

class RewardVPControl:
    def __init__(
        self,
        # -------------------------
        # VP control (PRIMARY)
        # -------------------------
        early_vp_reward: float = 0.50,     # Capture VP in turns 1–3
        normal_vp_reward: float = 0.25,    # Capture VP later
        hold_vp_reward: float = 0.15,      # Hold VP across turns
        lose_vp_penalty: float = 0.20,     # Lose VP

        # -------------------------
        # Tempo / urgency
        # -------------------------
        no_vp_by_turn3_penalty: float = 0.75,  # Strategic failure if no VP by turn 3

        # -------------------------
        # Casualties (SECONDARY)
        # -------------------------
        enemy_killed_reward: float = 0.25,
        own_unit_lost_penalty: float = 0.45,
    ):
        self.early_vp_reward = early_vp_reward
        self.normal_vp_reward = normal_vp_reward
        self.hold_vp_reward = hold_vp_reward
        self.lose_vp_penalty = lose_vp_penalty

        self.no_vp_by_turn3_penalty = no_vp_by_turn3_penalty

        self.enemy_killed_reward = enemy_killed_reward
        self.own_unit_lost_penalty = own_unit_lost_penalty

    def reset(self) -> None:
        # No internal state needed; all signals come from env info
        pass

    def compute(
        self,
        *,
        info: dict,
        episode_outcome=None,
    ) -> float:
        """
        Apply reward ONLY:
        - to RL-controlled side
        - at end of turn
        """

        # Apply ONLY to RL-controlled decisions
        if not info.get("is_rl", False):
            return 0.0

        # Apply ONLY at end of turn
        if not info.get("end_of_turn", False):
            return 0.0

        reward = 0.0

        current_turn = info.get("current_turn", 0)

        # --------------------------------------------------
        # VP CONTROL (PRIMARY OBJECTIVE)
        # --------------------------------------------------
        before = info.get("vp_control_before")
        after = info.get("vp_control_after")

        if before is not None and after is not None:
            # Gained a VP this turn
            if not before and after:
                if current_turn <= 3:
                    reward += self.early_vp_reward
                else:
                    reward += self.normal_vp_reward

            # Held VP
            elif before and after:
                reward += self.hold_vp_reward

            # Lost VP
            elif before and not after:
                reward -= self.lose_vp_penalty

        # --------------------------------------------------
        # CASUALTIES (SECONDARY)
        # --------------------------------------------------
        enemy_lost = info.get("enemy_units_lost", 0)
        own_lost = info.get("own_units_lost", 0)

        if enemy_lost:
            reward += enemy_lost * self.enemy_killed_reward

        if own_lost:
            reward -= own_lost * self.own_unit_lost_penalty

        # --------------------------------------------------
        # TEMPO RULE (SCENARIO-SPECIFIC)
        # --------------------------------------------------
        # If by the end of turn 3 we have captured no VP at all,
        # this represents a strategic failure per the campaign design.
        if current_turn == 3:
            total_vp = info.get("vp_total", 0)
            if total_vp == 0:
                reward -= self.no_vp_by_turn3_penalty

        return reward