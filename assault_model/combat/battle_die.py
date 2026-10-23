import random
from typing import Tuple, Dict

import orjson
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace


def _load_dice_face_table():
    from assault_model.paths import DICE_FACE_TABLE_PATH
    payload = orjson.loads(DICE_FACE_TABLE_PATH.read_bytes())
    raw = payload.get("dice_faces", {})
    parsed = {}
    for color_name, faces in raw.items():
        if color_name not in DiceColor.__members__:
            continue
        color = DiceColor[color_name]
        parsed_faces = []
        for symbols in faces:
            parsed_faces.append(tuple(DiceFace[s] for s in symbols))
        parsed[color] = parsed_faces
    return parsed


DICE_FACE_TABLE = _load_dice_face_table()


class DiceResult:
    """
    DiceResult

    Represents the exact outcome of rolling a single battle die.

    - color: the DiceColor of the die
    - faces: a tuple of DiceFace symbols
        * ()              -> blank face
        * (DAMAGE,)       -> single success
        * (CRITICAL, ...) -> critical success
        * two symbols     -> double success
    """

    __slots__ = ("color", "faces")

    def __init__(self, color: DiceColor, faces: Tuple[DiceFace, ...]):
        self.color = color
        self.faces = faces

    def __repr__(self) -> str:
        return f"DiceResult(color={self.color.name}, faces={[f.name for f in self.faces]})"


# Pre-allocated immutable results pool to eliminate per-roll allocation overhead
PREALLOCATED_DICE_RESULTS: Dict[DiceColor, Tuple[DiceResult, ...]] = {
    color: tuple(DiceResult(color, faces) for faces in faces_list)
    for color, faces_list in DICE_FACE_TABLE.items()
}


class BattleDie:
    """
    BattleDie

    Represents a single physical Assault battle die.
    """

    __slots__ = ("color", "_results")

    def __init__(self, color: DiceColor):
        self.color = color
        self._results = PREALLOCATED_DICE_RESULTS.get(color, ())

    def roll(self) -> DiceResult:
        """Roll and return a pre-allocated immutable DiceResult."""
        if not self._results:
            return DiceResult(self.color, ())
        return self._results[random.randint(0, len(self._results) - 1)]
