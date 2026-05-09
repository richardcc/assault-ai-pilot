from enum import Enum
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


class DiceFace(Enum):
    """
    DiceFace

    Represents a single combat symbol that can appear on a battle die,
    as defined by the Assault rulebook (section 10.7).

    IMPORTANT DESIGN NOTES
    ----------------------
    - A battle die MAY have a blank face.
    - A blank face produces NO combat symbols.
    - Therefore, BLANK is NOT a DiceFace.
    - Blank results are represented by an empty tuple () at the die level.

    This enum intentionally contains ONLY real combat symbols that
    participate in comparison and resolution:
        * CRITICAL
        * DAMAGE
        * SUPPRESS

    DiceFace does NOT:
    - Roll dice
    - Define probabilities
    - Know about die colors
    - Contain any game logic

    All rolling and probability handling is delegated to BattleDie.
    """

    CRITICAL = "CRITICAL"
    DAMAGE = "DAMAGE"
    SUPPRESS = "SUPPRESS"