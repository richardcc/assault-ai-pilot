class VPReward:

    def __init__(self):
        self.prev_vp = 0

    def compute(self, *, next_state, active):

        reward = 0.0

        current_vp = (
            next_state.vp_tracker.total_points
            if next_state.vp_tracker else 0
        )

        # ----------------------------------------
        # ✅ GANANCIA REAL DE VP
        # ----------------------------------------
        delta_vp = current_vp - self.prev_vp
        reward += 4.0 * delta_vp

        self.prev_vp = current_vp

        # ----------------------------------------
        # ✅ OCUPAR VP (SOLO SI GANAS PUNTOS)
        # ----------------------------------------
        if delta_vp > 0 and active and active.position and next_state.vp_tracker:

            for vp in next_state.vp_tracker.conditions.points:
                if (active.position.q, active.position.r) == vp.hex_coords:
                    reward += 0.8   # solo cuando capturas

        return reward