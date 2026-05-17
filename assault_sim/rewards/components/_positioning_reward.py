from assault_model.map.hex_utils import hex_distance


class PositioningReward:

    def compute(self, *, state, next_state, pre_dist, post_dist):

        reward = 0.0

        # ----------------------------------------
        # ✅ DISTANCIA A ENEMIGO (SUAVIZADA)
        # ----------------------------------------
        if pre_dist is not None and post_dist is not None:

            delta = pre_dist - post_dist

            # acercarse → OK
            reward += 0.2 * delta   # 🔧 antes 0.3

            # alejarse → castigo suave (ANTES era demasiado fuerte)
            if delta < 0:
                reward -= 0.2       # 🔧 antes -0.7 ❌

        # ----------------------------------------
        # ✅ DISTANCIA A VP (OK, pero suavizado)
        # ----------------------------------------
        if next_state.vp_tracker:
            vp_points = next_state.vp_tracker.conditions.points

            if vp_points:

                def min_dist(units):
                    return min(
                        hex_distance(u.position, vp.hex_coords)
                        for u in units
                        if u.position and u.alive
                        for vp in vp_points
                    )

                try:
                    pre_vp = min_dist(state.units)
                    post_vp = min_dist(next_state.units)

                    reward += 0.1 * (pre_vp - post_vp)   # 🔧 antes 0.2

                except ValueError:
                    pass

        return reward