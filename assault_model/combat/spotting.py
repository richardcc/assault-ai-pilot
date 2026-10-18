from assault_model.combat.line_of_sight import LineOfSight


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
    if any(str(t).upper() == "HIDDEN" for t in traits):
        has_fired = bool(getattr(target, "has_fired_this_turn", False))
        has_fast = bool(getattr(target, "has_fast_action_this_turn", False))
        if not (has_fired or has_fast):
            return False

    # --------------------------------------
    # BLOCKED → nunca visible
    # --------------------------------------
    if los == LineOfSight.BLOCKED:
        return False

    # --------------------------------------
    # HINDERED CASE
    # --------------------------------------
    if los == LineOfSight.HINDERED:

        # ✅ obtener hex correctamente
        hex_ = game_map.get_hex(target.position.q, target.position.r)

        if hex_:
            terrain = hex_.get_terrain()

            # ✅ usar API correcta
            config = terrain_config.get(terrain)

            # si además está en terreno que también cubre
            if config.get("los") == "HINDERED":
                return False

        # si solo la línea está entorpecida → sí visible
        return True

    # --------------------------------------
    # CLEAR → siempre visible
    # --------------------------------------
    return True
