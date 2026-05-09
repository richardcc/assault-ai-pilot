# assault_model/combat/dice_comparison.py
#
# Dice comparison logic according to Assault Rulebook 10.7.2
#
# Canonical implementation.
# Provides backward compatibility via `compare_dice`.
#
# IMPORTANT:
# - Supports BOTH new DiceResult and legacy (color, face) tuples.
# - This allows incremental migration without breaking simulations.

from collections import Counter
from typing import List, Iterable, Dict, Any

from assault_model.combat.dice_face import DiceFace
from assault_model.combat.battle_die import DiceResult


# Strength order: strongest first
_SYMBOL_ORDER = [
    DiceFace.CRITICAL,
    DiceFace.DAMAGE,
    DiceFace.SUPPRESS,
]


def _flatten_faces(dice_results: Iterable[Any]) -> List[DiceFace]:
    """
    Extract DiceFace symbols from dice results.

    Supported formats:
    - DiceResult(color, faces)
    - Legacy (color, face) tuples

    Blank faces produce no symbols.
    """
    faces: List[DiceFace] = []

    for die in dice_results:
        # ✅ New model: DiceResult
        if hasattr(die, "faces"):
            faces.extend(die.faces)

        # ✅ Legacy model: (color, face)
        elif isinstance(die, tuple) and len(die) == 2:
            _, face = die
            if face is not None:
                faces.append(face)

        else:
            raise TypeError(
                f"Unsupported dice result type: {type(die)} -> {die}"
            )

    return faces


def compare_dice(
    *,
    attacker_dice: List[DiceResult],
    defender_dice: List[DiceResult],
) -> Dict[str, int]:
    """
    Compare attacker and defender dice according to Assault Rulebook 10.7.2.

    Rule summary:
    - Each defender symbol cancels one attacker symbol of equal or weaker strength.
    - Cancellation is processed from strongest to weakest symbols.

    Returns:
        A dict with remaining (uncancelled) attacker symbols:
        {
            "remaining_damage": int,
            "remaining_criticals": int,
            "remaining_suppress": int,
        }
    """

    attacker_faces = Counter(_flatten_faces(attacker_dice))
    defender_faces = Counter(_flatten_faces(defender_dice))

    # Process defender symbols from strongest to weakest
    for defender_symbol in _SYMBOL_ORDER:
        while defender_faces[defender_symbol] > 0:
            # Find strongest cancellable attacker symbol
            for attacker_symbol in _SYMBOL_ORDER:
                if _SYMBOL_ORDER.index(attacker_symbol) >= _SYMBOL_ORDER.index(defender_symbol):
                    if attacker_faces[attacker_symbol] > 0:
                        attacker_faces[attacker_symbol] -= 1
                        defender_faces[defender_symbol] -= 1
                        break
            else:
                # Defender symbol cannot cancel anything
                break

    return {
        "remaining_damage": attacker_faces[DiceFace.DAMAGE],
        "remaining_criticals": attacker_faces[DiceFace.CRITICAL],
        "remaining_suppress": attacker_faces[DiceFace.SUPPRESS],
    }


