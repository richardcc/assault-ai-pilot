from enum import IntEnum
import os

# -------------------------------------------------
# Debug tracing (configurable via environment)
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class DiceColor(IntEnum):
    """
    DiceColor

    Represents the strength tier of a battle die, as defined by the
    Assault rulebook (sections 4.5 and 10.7).

    IMPORTANT DESIGN NOTES
    ----------------------
    - DiceColor expresses RELATIVE STRENGTH, not probability.
    - Higher numeric value means stronger die.
    - DiceColor does NOT define die faces or probabilities.
    - DiceColor does NOT roll dice.

    Strength order (strongest to weakest):
        RED    > YELLOW > GREEN > BLUE

    Probabilities are defined exclusively by the die face tables
    in BattleDie.
    """

    RED = 4
    YELLOW = 3
    GREEN = 2
    BLUE = 1

    @classmethod
    def sorted_strongest_first(cls):
        """
        Return all dice colors sorted by strength, strongest first.

        This method derives the order dynamically from enum values,
        avoiding hardcoded lists.
        """
        order = sorted(cls, key=lambda c: c.value, reverse=True)
        _trace("DICE_COLOR_ORDER", order=order)
        return order
