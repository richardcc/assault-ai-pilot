import random
from typing import Tuple

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace

# -------------------------------------------------
# Battle die face tables
# -------------------------------------------------
# Each entry represents one physical face of the die.
# An empty tuple () represents a blank face (no symbols).
# Tuples with two symbols represent a double success.
#
# These tables are derived from the official Assault
# dice reference and MUST NOT be generated procedurally.
# -------------------------------------------------

DICE_FACE_TABLE = {
    DiceColor.RED: [
        (DiceFace.DAMAGE, DiceFace.DAMAGE),
        (DiceFace.DAMAGE, DiceFace.SUPPRESS),
        (DiceFace.DAMAGE, DiceFace.DAMAGE),
        (DiceFace.DAMAGE, DiceFace.DAMAGE),
        (DiceFace.CRITICAL, DiceFace.DAMAGE),
        (),
    ],

    DiceColor.YELLOW: [
        (DiceFace.SUPPRESS,),
        (DiceFace.DAMAGE,),
        (DiceFace.DAMAGE,),
        (DiceFace.DAMAGE, DiceFace.DAMAGE),
        (DiceFace.CRITICAL, DiceFace.DAMAGE),
        (DiceFace.SUPPRESS, DiceFace.DAMAGE),
    ],

    DiceColor.GREEN: [
        (DiceFace.SUPPRESS,),
        (DiceFace.DAMAGE,),
        (DiceFace.DAMAGE,),
        (DiceFace.CRITICAL, DiceFace.DAMAGE),
        (DiceFace.DAMAGE,),
        (),
    ],

    DiceColor.BLUE: [
        (DiceFace.SUPPRESS,),
        (DiceFace.DAMAGE,),
        (DiceFace.DAMAGE,),
        (),
        (),
        (),
    ],
}


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