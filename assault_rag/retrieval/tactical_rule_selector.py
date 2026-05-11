from typing import List, Dict


# Mapping between observed facts and required rule concerns
FACT_TO_CONCERN = {
    "ACTION_EFFECT": {"DICE_RESOLUTION"},
    "remaining_damage": {"DAMAGE_ASSIGNMENT"},
    "remaining_criticals": {"DAMAGE_ASSIGNMENT"},
    "defender_hp_after": {"HP_ASSIGNMENT"},
    "attack_sector": {"IMPACT_SECTOR"},
}

# Hard guard keywords that must never appear for infantry ranged combat
FORBIDDEN_KEYWORDS_FOR_INFANTRY_RANGED = {
    "ARC",
    "FACING",
    "VEHICLE",
    "TURRET",
    "EMERGENCY",
    "DISEMBARK",
    "CLOSE COMBAT",
}


def is_ranged_combat(activation_events: List[Dict]) -> bool:
    """
    Return True if the activation contains a ranged attack.
    """
    return any(
        ev["type"] == "ACTION"
        and ev["payload"].get("action") == "RangedDirectAttack"
        for ev in activation_events
    )


def extract_required_concerns(activation_events: List[Dict]) -> set:
    """
    Determine which rule concerns are strictly required
    by the observed tactical facts.
    """
    required = set()

    for ev in activation_events:
        if ev["type"] == "ACTION_EFFECT":
            required |= FACT_TO_CONCERN["ACTION_EFFECT"]

            payload = ev["payload"]
            resolution = payload.get("resolution", {})

            if resolution.get("remaining_damage", 0) > 0:
                required |= FACT_TO_CONCERN["remaining_damage"]

            if payload.get("defender_hp_after") != payload.get("defender_hp_before"):
                required |= FACT_TO_CONCERN["defender_hp_after"]

            if payload.get("attack_sector"):
                required |= FACT_TO_CONCERN["attack_sector"]

    return required


def select_tactical_rules(
    typed_rules: List[Dict],
    activation_events: List[Dict],
    max_rules: int = 4,
) -> List[Dict]:
    """
    Select only rulebook rules strictly required
    to explain the observed tactical execution.
    """

    required_concerns = extract_required_concerns(activation_events)
    ranged = is_ranged_combat(activation_events)

    selected = []

    for rule in typed_rules:
        # Only resolution-phase rules are relevant here
        if rule.get("phase") != "RESOLUTION":
            continue

        rule_concerns = set(rule.get("concerns", []))
        rule_text = rule.get("text", "").upper()

        # ❌ Never allow spotting rules unless explicitly present in facts
        if "SPOTTING" in rule_concerns:
            continue

        # ❌ Hard guard: infantry ranged combat must not see vehicle / arc rules
        if ranged and any(keyword in rule_text for keyword in FORBIDDEN_KEYWORDS_FOR_INFANTRY_RANGED):
            continue

        # ✅ Rule must match concerns strictly required by observed facts
        if rule_concerns & required_concerns:
            selected.append(rule)

    # Prefer more specific rules
    selected.sort(
        key=lambda r: len(r.get("concerns", [])),
        reverse=True,
    )

    return selected[:max_rules]