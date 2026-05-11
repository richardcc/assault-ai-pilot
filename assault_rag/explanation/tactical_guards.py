def has_combat_effect(activation_events: list) -> bool:
    """
    Return True if the activation contains a combat resolution.
    """
    return any(ev["type"] == "ACTION_EFFECT" for ev in activation_events)