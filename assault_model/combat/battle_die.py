import random
import json
from pathlib import Path
from typing import Tuple

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace

def _load_dice_face_table():
    table_path = (
        Path(__file__).resolve().parents[2]
        / "assault_sim"
        / "assets"
        / "rules_tables"
        / "combat"
        / "dice_face_table.v1.json"
    )
    payload = json.loads(table_path.read_text(encoding="utf-8"))
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


class BattleDie:
    """
    BattleDie

    Represents a single physical Assault battle die.

    Responsibilities:
    - Know its color
    - Know its face table
    - Roll and return an exact DiceResult

    BattleDie does NOT:
    - Apply combat rules
    - Compare dice
    - Calculate damage
    - Know about units or combat context
    """

    def __init__(self, color: DiceColor):
        self.color = color

    def roll(self) -> DiceResult:
        faces = random.choice(DICE_FACE_TABLE[self.color])
        return DiceResult(self.color, faces)