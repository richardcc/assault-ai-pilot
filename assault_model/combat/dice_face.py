from enum import Enum
import os

# DEBUG TRACE (configurable por entorno)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class DiceFace(Enum):
    CRITICAL = "CRITICAL"
    DAMAGE = "DAMAGE"
    SUPPRESS = "SUPPRESS"
    BLANK = "BLANK"

    @classmethod
    def roll(cls):
        import random
        face = random.choice(list(cls))
        _trace("DICE_FACE_ROLL", face=face.name)
        return face