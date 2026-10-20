from typing import Optional
from dataclasses import dataclass
import random
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


@dataclass
class MineDetectionResult:
    """
    Result of a mine detection / scouting test (Rule 9.6.6.2 & Combat Engineers card).
    """
    success: bool
    d6_roll: int
    modifiers: int
    total_score: int
    target_threshold: int
    was_dummy: bool
    identified: bool


def calculate_detection_modifiers(
    unit,
    is_unhidden: bool = False,
    is_fallback: bool = False,
    command_bonus: int = 0,
) -> int:
    """
    Calculate detection roll modifiers according to Rule 9.6.6.2 table.
    - MINE_DETECTION trait: +2
    - SCOUT trait: +1
    - Unhidden minefield: +1
    - Fallback: -1
    - Command card effect: +command_bonus
    """
    mod = 0
    traits = getattr(getattr(unit, "unit_type", None), "traits", []) or []
    trait_set = {str(t).upper() for t in traits}

    if "MINE_DETECTION" in trait_set:
        mod += 2
    if "SCOUT" in trait_set:
        mod += 1
    if is_unhidden:
        mod += 1
    if is_fallback or getattr(unit, "fallback", False):
        mod -= 1
    mod += command_bonus
    return mod


def resolve_mine_detection(
    action,
    scout_unit,
    game_map,
    game_state=None,
    context=None,
    injected_d6: Optional[int] = None,
) -> MineDetectionResult:
    """
    Resolve minefield detection / reconnaissance (Rule 9.6.6.2).

    Base target:
    - Infantry: 5+
    - Artillery / Vehicle: 6+
    """
    tq, tr = action.target_hex

    # Determine base threshold
    cat = getattr(getattr(scout_unit, "unit_type", None), "category", None)
    cat_name = getattr(cat, "name", str(cat)).upper()
    is_infantry = "INFANTRY" in cat_name
    base_threshold = 5 if is_infantry else 6

    # Fortification data
    fort_data = game_map.get_hex_fortification_data(tq, tr) if game_map else None
    fort_type = game_map.get_hex_fortification(tq, tr) if game_map else None
    is_identified = bool(fort_data.get("identified", False)) if fort_data else False
    is_dummy = fort_type == "dummy_minefield"

    # Modifiers
    mods = calculate_detection_modifiers(scout_unit, is_unhidden=is_identified)

    # Roll D6
    d6 = random.randint(1, 6) if injected_d6 is None else int(injected_d6)
    total_score = d6 + mods

    success = total_score >= base_threshold

    _trace(
        "MINE_DETECTION_ROLL",
        unit=scout_unit.unit_id,
        target=(tq, tr),
        d6=d6,
        mods=mods,
        total=total_score,
        target_threshold=base_threshold,
        success=success,
    )

    if success:
        if is_dummy:
            if game_map:
                game_map.remove_hex_fortification(tq, tr)
            identified = True
        else:
            if game_map:
                game_map.set_hex_fortification_identified(tq, tr, True)
            identified = True
    else:
        identified = is_identified

    return MineDetectionResult(
        success=success,
        d6_roll=d6,
        modifiers=mods,
        total_score=total_score,
        target_threshold=base_threshold,
        was_dummy=is_dummy,
        identified=identified,
    )
