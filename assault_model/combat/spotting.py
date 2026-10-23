from assault_model.combat.line_of_sight import LineOfSight
from assault_model.map.hex_utils import safe_hex_distance


def calculate_spotting_modifier(attacker, target, los=None) -> int:
    """
    Calculate the net D6 modifier applied to attacker's spotting rolls against the target.
    (Rulebook §10.5 Direct Fire Spotting, §12.3.6.2 TAS Accuracy, §12.4.2.1 OAS Spotting)

    - Hindering terrain along LOS: -1 modifier (Rule §10.5)
    - Target has LOW_SILHOUETTE: -1 modifier ("When defending, -1 modifier to spotting rolls for the attacker")
    - Target has TALL_SILHOUETTE / SILHOUETTE: +1 modifier ("When defending, +1 modifier to spotting rolls for the attacker")
    """
    modifier = 0

    if los == LineOfSight.HINDERED:
        modifier -= 1

    traits = getattr(getattr(target, "unit_type", None), "traits", []) or []
    trait_names = {str(t).upper() for t in traits}

    if "LOW_SILHOUETTE" in trait_names:
        modifier -= 1

    if "TALL_SILHOUETTE" in trait_names or "SILHOUETTE" in trait_names:
        modifier += 1

    return modifier


def can_spot(attacker, target, los, game_map, terrain_config):
    """
    Deterministic spotting logic (rule-consistent).

    LOS already encodes terrain obstruction.
    """

    # --------------------------------------
    # HIDDEN trait (Rule: Automatic spotting never applies.
    # Can only be spotted when marked with fire status marker or fast action)
    # --------------------------------------
    traits = getattr(getattr(target, "unit_type", None), "traits", []) or []
    trait_names = {str(t).upper() for t in traits}

    has_fired = bool(getattr(target, "has_fired_this_turn", False))
    has_fast = bool(getattr(target, "has_fast_action_this_turn", False))

    if "HIDDEN" in trait_names:
        if not (has_fired or has_fast):
            return False

    # --------------------------------------
    # CONCEALED / CAMOUFLAGED traits
    # Units in covering or hindering terrain remain undetected at range (>1 hex)
    # unless they reveal their position by firing or taking a fast action.
    # --------------------------------------
    if ("CONCEALED" in trait_names or "CAMOUFLAGED" in trait_names) and not (has_fired or has_fast):
        hex_ = game_map.get_hex(target.position.q, target.position.r) if game_map else None
        if hex_:
            terrain = hex_.get_terrain()
            is_covering = False
            if hasattr(terrain_config, "get"):
                cfg = terrain_config.get(terrain)
                if isinstance(cfg, dict):
                    is_covering = (
                        cfg.get("los") in ("HINDERED", "BLOCKED")
                        or bool(cfg.get("defense", {}).get("INFANTRY"))
                        or bool(cfg.get("defense", {}).get("VEHICLE"))
                    )
            elif hasattr(terrain_config, "get_defense_dice"):
                dice = terrain_config.get_defense_dice(terrain, "INFANTRY") or terrain_config.get_defense_dice(terrain, "VEHICLE")
                is_covering = bool(dice) or terrain not in ("clear", "open")

            if is_covering:
                dist = safe_hex_distance(attacker.position, target.position) if hasattr(attacker, "position") and hasattr(target, "position") else 2
                if dist > 1:
                    return False

    # --------------------------------------
    # LOW_SILHOUETTE trait
    # Card Rule: "When defending, -1 modifier to spotting rolls for the attacker."
    # Low-profile defending units in terrain with defense bonus or under hindered LOS
    # cannot be spotted at range unless they reveal themselves.
    # --------------------------------------
    if "LOW_SILHOUETTE" in trait_names and not (has_fired or has_fast):
        hex_ = game_map.get_hex(target.position.q, target.position.r) if game_map else None
        if hex_:
            terrain = hex_.get_terrain()
            has_defense_bonus = False
            if hasattr(terrain_config, "get"):
                cfg = terrain_config.get(terrain)
                if isinstance(cfg, dict):
                    has_defense_bonus = (
                        bool(cfg.get("defense", {}).get("INFANTRY"))
                        or bool(cfg.get("defense", {}).get("VEHICLE"))
                        or cfg.get("los") in ("HINDERED", "BLOCKED")
                    )
            elif hasattr(terrain_config, "get_defense_dice"):
                dice = terrain_config.get_defense_dice(terrain, "INFANTRY") or terrain_config.get_defense_dice(terrain, "VEHICLE")
                has_defense_bonus = bool(dice) or terrain not in ("clear", "open")

            if has_defense_bonus:
                dist = safe_hex_distance(attacker.position, target.position) if hasattr(attacker, "position") and hasattr(target, "position") else 2
                if dist > 1:
                    return False

    # --------------------------------------
    # BLOCKED -> never visible
    # --------------------------------------
    if los == LineOfSight.BLOCKED:
        return False

    # --------------------------------------
    # HINDERED CASE
    # --------------------------------------
    if los == LineOfSight.HINDERED:
        # TALL_SILHOUETTE (+1 spotting bonus) counters hindered concealment at medium range (<= 3 hexes)
        if "TALL_SILHOUETTE" in trait_names or "SILHOUETTE" in trait_names:
            dist = safe_hex_distance(attacker.position, target.position) if hasattr(attacker, "position") and hasattr(target, "position") else 2
            if dist <= 3:
                return True

        # Obtain target hex correctly
        hex_ = game_map.get_hex(target.position.q, target.position.r) if game_map else None

        if hex_:
            terrain = hex_.get_terrain()

            # Check if target is inside covering terrain
            if hasattr(terrain_config, "get"):
                config = terrain_config.get(terrain)
                if isinstance(config, dict) and config.get("los") == "HINDERED":
                    return False

        # If only line is hindered -> visible
        return True

    # --------------------------------------
    # CLEAR -> visible
    # --------------------------------------
    return True
