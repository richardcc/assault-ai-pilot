from assault_model.map.hex_utils import safe_hex_distance



def compute_tactical_features(state, rl_side):
    """
    Computes high-level tactical features for RL policy.

    Returns:
        List[float]
    """

    # ----------------------------------
    # UNITS
    # ----------------------------------
    own_units = [
        u for u in state.units
        if u.side == rl_side and getattr(u, "alive", True) and u.position is not None
    ]

    enemy_units = [
        u for u in state.units
        if u.side != rl_side and getattr(u, "alive", True) and u.position is not None
    ]

    # ----------------------------------
    # SAFE FALLBACK
    # ----------------------------------
    if not own_units:
        return [1.0, 1.0, 0.0, 0.0, 1.0]

    unit = own_units[0]

    # ----------------------------------
    # HEALTH
    # ----------------------------------
    max_hp = getattr(unit, "max_hp", 4)
    health_ratio = unit.hp / max(max_hp, 1)

    # ----------------------------------
    # ENEMY DISTANCE
    # ----------------------------------
    if enemy_units:
        min_dist = min(
            safe_hex_distance(unit.position, e.position)
            for e in enemy_units
        )
    else:
        min_dist = 10

    enemy_dist_norm = min_dist / 10.0

    # ----------------------------------
    # THREAT LEVEL
    # ----------------------------------
    close_enemies = sum(
        1 for e in enemy_units
        if safe_hex_distance(unit.position, e.position) <= 3
    )
    threat_level = close_enemies / 5.0

    # ----------------------------------
    # ALLY SUPPORT
    # ----------------------------------
    close_allies = sum(
        1 for a in own_units
        if a.unit_id != unit.unit_id and
        safe_hex_distance(unit.position, a.position) <= 3
    )
    ally_support = close_allies / 5.0

    # ----------------------------------
    # ADVANTAGE
    # ----------------------------------
    advantage = ally_support / (threat_level + 0.1)

    return [
        health_ratio,
        enemy_dist_norm,
        threat_level,
        ally_support,
        advantage
    ]
