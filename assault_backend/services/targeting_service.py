from assault_model.map.hex_utils import safe_hex_distance
from assault_model.map.hex_coord import HexCoord
from assault_model.combat.line_of_sight import check_line_of_sight, LineOfSight
from assault_model.map.combat_geometry import determine_attack_sector
from assault_model.rules.fortification_rules import FortificationRules


def _color_names(dice):
    """Normalize a list of DiceColor/str into a list of color-name strings."""
    names = []
    for d in dice:
        name = getattr(d, "name", None)
        names.append(name if name is not None else str(d))
    return names


def _compute_combat_dice(attacker, target, distance, los, game_map):
    """
    Compute attack/defense dice BEFORE and AFTER modifiers.

    Mirrors the logic in ranged_combat_resolver without rolling:
    - attack: base from unit card; suppressed attacker loses last die
    - defense: base from sector; + terrain bonus; + HINDERED extra die
    """
    terrain_config = game_map.terrain_config

    # Fire mode (consistent with ActionCatalog / resolver)
    attack_mode = attacker.unit_type._resolve_attack_mode(distance)
    is_indirect = attack_mode == "INDIRECT_FIRE"

    # ---------------- ATTACK ----------------
    attack_base = list(
        attacker.unit_type.get_attack_dice(
            distance=distance,
            target_category=target.unit_type.category,
        )
    )

    attack_mod = list(attack_base)
    if getattr(attacker, "suppressed", False) and attack_mod:
        # Rulebook 10.8.1: a suppressed attacker loses its WEAKEST attack die.
        weakest = min(attack_mod, key=lambda c: int(c))
        attack_mod.remove(weakest)

    # ---------------- DEFENSE ----------------
    sector = determine_attack_sector(
        attacker_pos=attacker.position,
        defender_pos=target.position,
        defender_facing=getattr(target, "facing", "N"),
    )

    defense_base = list(target.unit_type.get_defense_dice(sector=sector))
    defense_mod = list(defense_base)
    terrain_bonus = []
    fort_bonus = []
    fort_type = None

    hex_ = game_map.get_hex(target.position.q, target.position.r)
    if hex_:
        terrain_name = hex_.get_terrain()
        terrain_bonus = terrain_config.get_defense_dice(
            terrain_name,
            target.unit_type.category.name,
        )
        defense_mod = defense_mod + list(terrain_bonus)
        fort_type = game_map.get_hex_fortification(target.position.q, target.position.r)
        fort_bonus = FortificationRules.defense_bonus(
            fort_type=fort_type,
            unit_category=target.unit_type.category.name,
            sector=sector,
        )
        defense_mod = defense_mod + list(fort_bonus)

    # Indirect fire has no LOS line → no HINDERED defense die.
    hindered = (not is_indirect) and los == LineOfSight.HINDERED
    if hindered:
        defense_mod = defense_mod + ["GREEN"]

    return {
        "attack": {
            "base": _color_names(attack_base),
            "modified": _color_names(attack_mod),
        },
        "defense": {
            "base": _color_names(defense_base),
            "modified": _color_names(defense_mod),
            "terrain_bonus": _color_names(terrain_bonus),
            "fortification_bonus": _color_names(fort_bonus),
            "fortification_type": fort_type,
        },
        "sector": getattr(sector, "name", str(sector)),
        "suppressed": bool(getattr(attacker, "suppressed", False)),
        "hindered": hindered,
        "indirect": is_indirect,
    }


def _compute_empty_hex_dice_preview(attacker, target_q: int, target_r: int, distance: int, los, game_map):
    """
    Preview defense modifiers on an empty hex (no target unit present).

    Convention:
    - Show hex-based defensive environment as if an infantry target occupied it.
    - No base defense dice (because there is no unit card).
    """
    terrain_config = game_map.terrain_config
    attack_mode = attacker.unit_type._resolve_attack_mode(distance)
    is_indirect = attack_mode == "INDIRECT_FIRE"

    hex_ = game_map.get_hex(target_q, target_r)
    if hex_ is None:
        return None

    terrain_name = hex_.get_terrain()
    terrain_bonus = list(terrain_config.get_defense_dice(terrain_name, "INFANTRY"))
    fort_type = game_map.get_hex_fortification(target_q, target_r)
    # Sector is irrelevant without defender facing; use FRONT as stable preview convention.
    fort_bonus = FortificationRules.defense_bonus(
        fort_type=fort_type,
        unit_category="INFANTRY",
        sector=determine_attack_sector(attacker.position, HexCoord(target_q, target_r), "N"),
    )

    defense_mod = list(terrain_bonus) + list(fort_bonus)
    hindered = (not is_indirect) and los == LineOfSight.HINDERED
    if hindered:
        defense_mod = defense_mod + ["GREEN"]

    return {
        "attack": {
            "base": [],
            "modified": [],
        },
        "defense": {
            "base": [],
            "modified": _color_names(defense_mod),
            "terrain_bonus": _color_names(terrain_bonus),
            "fortification_bonus": _color_names(fort_bonus),
            "fortification_type": fort_type,
        },
        "sector": "PREVIEW_HEX",
        "suppressed": bool(getattr(attacker, "suppressed", False)),
        "hindered": hindered,
        "indirect": is_indirect,
    }


def compute_targeting_info(game_state, attacker_id: str, target_q: int, target_r: int):
    """
    Returns:
    {
        "distance": int,
        "los": "CLEAR|HINDERED|BLOCKED",
        "path": [(q, r), ...],
        "blocking": [(q, r), ...],
        "hindrance": [(q, r), ...],
        "dice": {
            "attack":  {"base": [...], "modified": [...]},
            "defense": {"base": [...], "modified": [...]},
            ...
        } | None
    }
    """

    # ✅ buscar atacante
    attacker = next(
        (u for u in game_state.units if u.unit_id == attacker_id),
        None
    )

    if attacker is None or not attacker.alive:
        return None

    # ✅ posición target (hex)
    target_pos = HexCoord(target_q, target_r)

    # ✅ dummy target
    class DummyTarget:
        def __init__(self, pos):
            self.position = pos

    target = DummyTarget(target_pos)

    # ✅ DISTANCIA REAL
    distance = safe_hex_distance(attacker.position, target_pos)

    # ✅ LOS REAL (esto también rellena _los_debug)
    los = check_line_of_sight(
        attacker,
        target,
        game_state.game_map,
        game_state.game_map.terrain_config
    )

    # -------------------------------------------------
    # ✅ PATH (same ray as LOS terrain check)
    # -------------------------------------------------
    los_debug = getattr(attacker, "_los_debug", {})
    full_path = los_debug.get("path", [])
    path = full_path[1:-1] if len(full_path) > 2 else []

    blocking = los_debug.get("blocking", [])
    hindrance = los_debug.get("hindrance", [])

    # -------------------------------------------------
    # ✅ DICE (base + modified) when a real unit is on the target hex
    # -------------------------------------------------
    target_unit = next(
        (
            u for u in game_state.units
            if u.alive
            and u.position is not None
            and u.position.q == target_q
            and u.position.r == target_r
        ),
        None
    )

    dice = None
    if target_unit is not None:
        try:
            dice = _compute_combat_dice(
                attacker,
                target_unit,
                distance,
                los,
                game_state.game_map,
            )
        except Exception as e:
            print("[WARN][targeting] dice computation failed:", str(e))
            dice = None
    else:
        # Still provide terrain/fortification defense preview on empty hexes.
        try:
            dice = _compute_empty_hex_dice_preview(
                attacker,
                target_q,
                target_r,
                distance,
                los,
                game_state.game_map,
            )
        except Exception as e:
            print("[WARN][targeting] empty-hex preview failed:", str(e))
            dice = None

    if dice is not None:
        print(
            "[FORT_HOVER_DEBUG]"
            f" attacker={attacker.unit_id}"
            f" target_hex=({target_q},{target_r})"
            f" sector={dice.get('sector')}"
            f" fort={dice.get('defense', {}).get('fortification_type')}"
            f" fort_bonus={dice.get('defense', {}).get('fortification_bonus')}"
            f" terrain_bonus={dice.get('defense', {}).get('terrain_bonus')}"
            f" defense_final={dice.get('defense', {}).get('modified')}"
        )

    # -------------------------------------------------
    # RETURN
    # -------------------------------------------------
    return {
        "distance": distance,
        "los": los.name,
        "path": path,
        "path_full": full_path,
        "blocking": blocking,
        "hindrance": hindrance,
        "dice": dice,
    }
