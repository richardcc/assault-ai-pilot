import random


class HeuristicAgent:
    """
    VP-aware enemy heuristic.

    - ε-greedy exploration
    - ALWAYS assaults if in range
    - Actively defends and recaptures Victory Points (VP)
    """

    def __init__(self, epsilon: float = 0.2):
        self.epsilon = epsilon

    def act(
        self,
        obs,
        *,
        enemy_pos,
        player_pos,
        vp_hexes,
        vp_controlled_by_player
    ) -> int:
        # --------------------------------------------------
        # SAFETY: unwrap Gym-style (obs, info)
        # --------------------------------------------------
        if isinstance(obs, tuple):
            obs = obs[0]

        # --------------------------------------------------
        # ε-GREEDY EXPLORATION
        # --------------------------------------------------
        if random.random() < self.epsilon:
            return random.randint(0, 6)

        # --------------------------------------------------
        # ALWAYS ASSAULT IF POSSIBLE
        # --------------------------------------------------
        if bool(obs.get("can_assault", [0])[0]):
            return 2  # ASSAULT

        # --------------------------------------------------
        # DETERMINE TARGET VP
        # --------------------------------------------------
        if vp_controlled_by_player:
            # Recapture VP controlled by the player
            targets = list(vp_controlled_by_player)
        else:
            # Otherwise advance toward nearest VP
            targets = list(vp_hexes)

        if not targets:
            return 0  # WAIT (should not happen)

        ex, ey = enemy_pos
        tx, ty = min(
            targets,
            key=lambda p: abs(p[0] - ex) + abs(p[1] - ey)
        )

        dx = tx - ex
        dy = ty - ey

        # --------------------------------------------------
        # MOVE TOWARD TARGET
        # --------------------------------------------------
        if abs(dx) > abs(dy):
            return 1 if dx > 0 else 6   # MOVE_FORWARD / MOVE_BACKWARD
        else:
            return 4 if dy > 0 else 5   # MOVE_LEFT / MOVE_RIGHT