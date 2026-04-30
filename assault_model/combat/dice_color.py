from enum import IntEnum
import os

# DEBUG TRACE (configurable por entorno)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class DiceColor(IntEnum):
    RED = 4
    YELLOW = 3
    GREEN = 2
    BLUE = 1

    @classmethod
    def strongest_first(cls):
        order = [cls.RED, cls.YELLOW, cls.GREEN, cls.BLUE]
        _trace("DICE_COLOR_ORDER", order=order)
        return order