def explain_activation_facts(events: list) -> str:
    """
    Deterministic tactical facts.
    """
    for ev in events:
        if ev["type"] == "ACTION_EFFECT":
            p = ev["payload"]
            return (
                f"{p['attacker']} attacked {p['defender']} at distance "
                f"{p['distance']} from the {p['attack_sector']} sector. "
                f"{p['resolution']['remaining_damage']} damage and "
                f"{p['resolution']['remaining_criticals']} critical symbols "
                f"remained uncancelled, reducing HP from "
                f"{p['defender_hp_before']} to {p['defender_hp_after']}."
            )
    return "The unit performed the action without combat."


def explain_tactical_rules(events: list, rulebook: dict) -> str:
    """
    Dice-based explanation using ONLY observed facts.
    """

    for ev in events:
        if ev["type"] == "ACTION_EFFECT":
            p = ev["payload"]
            res = p["resolution"]

            return (
                "According to the standard ranged combat resolution rules, "
                "attack and defense dice are compared and opposing symbols "
                "cancel each other. "
                f"After cancellation, {res['remaining_damage']} damage and "
                f"{res['remaining_criticals']} critical symbols remained, "
                f"which were applied to the defender."
            )

    return "No combat rules were applied during this activation."