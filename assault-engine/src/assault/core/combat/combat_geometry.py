"""
Combat geometry utilities.

Responsible for determining attack sectors (front, flank, rear)
based purely on relative positions.
"""

def compute_attack_sector(
    attacker_pos: tuple[int, int],
    defender_pos: tuple[int, int],
) -> str:
    """
    Determines attack sector based on relative positions.

    Returns:
        "FRONT"
        "FLANK_LEFT"
        "FLANK_RIGHT"
        "REAR"
    """

    ax, ay = attacker_pos
    dx, dy = defender_pos

    vx = dx - ax
    vy = dy - ay

    if abs(vx) > abs(vy):
        if vx > 0:
            return "FRONT"
        else:
            return "REAR"
    else:
        if vy > 0:
            return "FLANK_RIGHT"
        else:
            return "FLANK_LEFT"