from assault_model.combat.line_of_sight import LineOfSight


def can_spot(attacker, target, los, game_map, terrain_config):
    """
    Deterministic spotting logic (rule-consistent).

    LOS already encodes terrain obstruction.
    """

    # --------------------------------------
    # BLOCKED → nunca visible
    # --------------------------------------
    if los == LineOfSight.BLOCKED:
        return False

    # --------------------------------------
    # HINDERED CASE
    # --------------------------------------
    if los == LineOfSight.HINDERED:

        # terreno del objetivo
        hex_ = game_map.get_hex(target.position)

        if hex_:
            terrain = hex_.get_terrain()
            config = terrain_config.get(terrain, {})

            # si además está en terreno que también cubre
            if config.get("los") == "HINDERED":
                return False

        # si solo la línea está entorpecida → sí visible
        return True

    # --------------------------------------
    # CLEAR → siempre visible
    # --------------------------------------
    return True