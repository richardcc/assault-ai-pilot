def resolve_terrain(hex_):
    """
    Returns the effective terrain of a hex.

    Priority:
    1. terrain defined in state (if any)
    2. base terrain
    """

    state = getattr(hex_, "state", None)

    if state:
        # explicit ordering = no ambiguity
        if getattr(state, "building_multi", False):
            return "building_multi"

        if getattr(state, "building_single", False):
            return "building_single"

        if getattr(state, "heavy_forest", False):
            return "heavy_forest"

        if getattr(state, "light_forest", False):
            return "light_forest"

        if getattr(state, "olive_vine_grove", False):
            return "olive_vine_grove"

        if getattr(state, "rocky", False):
            return "rocky"

    return hex_.terrain.value