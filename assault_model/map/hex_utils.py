def hex_distance(a, b):
    """
    Axial hex distance between (q, r) coordinates.

    Uses cube-distance projection:
    distance = max(|dq|, |dr|, |dq + dr|)
    """
    aq, ar = a
    bq, br = b

    return max(
        abs(aq - bq),
        abs(ar - br),
        abs((aq + ar) - (bq + br)),
    )
