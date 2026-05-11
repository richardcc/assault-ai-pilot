def extract_rl_activations(turn_events: list) -> list:
    """
    Extract activations for RL-controlled units from a turn.

    Each activation contains:
    - unit
    - action
    - start_index (index in turn_events where ACTION occurs)
    - events (ACTION + all sub-events)
    """

    activations = []
    current = None

    for idx, ev in enumerate(turn_events):
        if ev["type"] == "ACTION":
            payload = ev["payload"]
            unit = payload.get("active_unit")

            # Close previous activation
            if current is not None:
                activations.append(current)
                current = None

            # Start activation only for RL units (US_*)
            if unit and unit.startswith("US_"):
                current = {
                    "unit": unit,
                    "action": payload.get("action"),
                    "start_index": idx,   # ✅ CLAVE
                    "events": [ev],
                }

        else:
            if current is not None:
                current["events"].append(ev)

    # Close last activation
    if current is not None:
        activations.append(current)

    return activations