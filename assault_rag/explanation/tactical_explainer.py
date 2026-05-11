def explain_tactical_action(payload: dict) -> str:
    """
    Minimal tactical explainer based only on replay facts.
    """

    attacker = payload.get("attacker")
    defender = payload.get("defender")
    distance = payload.get("distance")
    sector = payload.get("attack_sector")

    hp_before = payload.get("defender_hp_before")
    hp_after = payload.get("defender_hp_after")

    remaining_damage = payload.get("resolution", {}).get("remaining_damage", 0)
    remaining_criticals = payload.get("resolution", {}).get("remaining_criticals", 0)

    return (
        f"{attacker} executed a ranged attack against {defender} "
        f"at distance {distance} from the {sector} sector. "
        f"After combat resolution, {remaining_damage} damage and "
        f"{remaining_criticals} critical symbols remained uncancelled, "
        f"reducing the defender's HP from {hp_before} to {hp_after}."
    )