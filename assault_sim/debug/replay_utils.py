def extract_initial_state(game_state):
    """
    Extract minimal initial state for replay purposes.

    Uses the real UnitInstance + UnitType API.
    """

    units = []

    for unit in game_state.units:
        if unit.position is None:
            q = None
            r = None
        else:
            q = unit.position.q
            r = unit.position.r

        units.append({
            "id": unit.unit_id,
            "q": q,
            "r": r,
            "hp": unit.hp,
            "side": unit.side,
            "type": unit.unit_type.code,
        })

    return {
        "turn": game_state.turn,
        "units": units,
    }