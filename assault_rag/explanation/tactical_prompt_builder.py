from typing import List, Dict


def format_dice(dice_list: List[Dict]) -> str:
    """
    Format dice information for the tactical prompt.
    """
    parts = []
    for die in dice_list:
        faces = ", ".join(die.get("faces", [])) if die.get("faces") else "blank"
        parts.append(f"{die.get('color')} die [{faces}]")
    return "; ".join(parts)


def format_activation_facts(activation_events: List[Dict]) -> str:
    """
    Convert activation events into a concise factual description
    to be used inside the tactical prompt, including dice results.
    """

    lines = []

    for ev in activation_events:
        if ev["type"] == "ACTION":
            p = ev["payload"]
            lines.append(
                f"- Action: {p.get('action')} by unit {p.get('active_unit')}"
            )

        elif ev["type"] == "UNIT_MOVED":
            p = ev["payload"]
            src = p["from"]
            dst = p["to"]
            lines.append(
                f"- Movement: from ({src['q']},{src['r']}) "
                f"to ({dst['q']},{dst['r']})"
            )

        elif ev["type"] == "ACTION_EFFECT":
            p = ev["payload"]
            res = p.get("resolution", {})

            lines.append(
                f"- Combat: {p.get('attacker')} attacked {p.get('defender')} "
                f"at distance {p.get('distance')} from sector {p.get('attack_sector')}"
            )

            # ✅ Explicit dice (critical to prevent LLM invention)
            lines.append(
                f"  Attacker dice: {format_dice(p.get('attacker_attack_dice', []))}"
            )

            lines.append(
                f"  Defender dice: {format_dice(p.get('defender_defense_dice', []))}"
            )

            lines.append(
                f"  Remaining symbols after cancellation: "
                f"{res.get('remaining_damage', 0)} damage, "
                f"{res.get('remaining_criticals', 0)} criticals"
            )

            lines.append(
                f"  Defender HP: {p.get('defender_hp_before')} "
                f"→ {p.get('defender_hp_after')}"
            )

    return "\n".join(lines)


def build_tactical_prompt(
    activation_events: List[Dict],
    tactical_rules: List[Dict],
) -> str:
    """
    Build a prompt for explaining Tactical Execution
    using only observed activation events and rulebook rules.
    """

    facts_text = format_activation_facts(activation_events)

    rules_text = "\n\n".join(
        f"Rule {r['rule_id']}:\n{r['text']}"
        for r in tactical_rules
    )

    prompt = f"""
You are an expert analyst of the Assault ruleset.

Observed tactical execution (facts from the replay):
{facts_text}

Relevant rules from the official rulebook:
{rules_text}

Instructions:
- Explain ONLY how the observed tactical result occurred according to the rules.
- Do NOT explain why the action was chosen.
- Do NOT mention strategic intent or HRL decisions.
- Do NOT compare alternative actions.
- Do NOT invent mechanics or rules not listed above.
- If a rule concept is not explicitly mentioned in the observed facts, do NOT apply or reference it.

Explain the tactical execution.
""".strip()

    return prompt