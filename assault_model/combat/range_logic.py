# assault_model/combat/range_logic.py
"""
Range logic utilities.

This module translates geometric distance into combat semantics
(RangeBand). It belongs to the combat domain (NOT to actions,
resolvers, or enums).
"""

from assault_model.combat.range_band import RangeBand


def distance_to_range_band(distance: int) -> RangeBand:
    """
    Convert hex distance to a RangeBand.

    Mapping is aligned with unit card bands:

    - 0        -> CLOSE
    - 1–3      -> SHORT
    - 4–7      -> MEDIUM
    - 8+       -> LONG
    """
    if distance <= 0:
        return RangeBand.CLOSE
    if 1 <= distance <= 3:
        return RangeBand.SHORT
    if 4 <= distance <= 7:
        return RangeBand.MEDIUM
    return RangeBand.LONG