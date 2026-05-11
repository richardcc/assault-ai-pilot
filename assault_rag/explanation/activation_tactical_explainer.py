def explain_activation_events(events: list) -> str:
    """
    Explain all tactical events of a single activation.
    """
    action_event = events[0]
    payload = action_event["payload"]

    unit = payload.get("active_unit")
    action = payload.get("action")

    text = [f"{unit} was activated and performed a {action}."]

    for ev in events[1:]:
        if ev["type"] == "UNIT_MOVED":
            src = ev["payload"]["from"]
            dst = ev["payload"]["to"]
            text.append(
                f"The unit moved from ({src['q']},{src['r']}) "
                f"to ({dst['q']},{dst['r']})."
            )

        elif ev["type"] == "ACTION_EFFECT":
            p = ev["payload"]
            text.append(
                f"It engaged {p['defender']} at distance {p['distance']} "
                f"from the {p['attack_sector']} sector. "
                f"{p['resolution']['remaining_damage']} damage and "
                f"{p['resolution']['remaining_criticals']} critical symbols "
                f"remained uncancelled, reducing HP from "
                f"{p['defender_hp_before']} to {p['defender_hp_after']}."
            )

    return " ".join(text)