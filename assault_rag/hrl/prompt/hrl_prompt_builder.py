from typing import Dict, List

def build_hrl_prompt(decision: Dict, principles: List[Dict]) -> str:
    """
    Build a prompt for explaining a HRL_DECISION using retrieved strategic principles.
    """

    option = decision.get("option")
    category = decision.get("category")
    context = decision.get("context", {})
    policy = decision.get("policy_info", {})

    friendly = context.get("friendly_strength", "UNKNOWN")
    pressure = context.get("enemy_pressure", "UNKNOWN")
    objective = context.get("objective_distance", "UNKNOWN")

    value = policy.get("value_estimate", None)
    confidence = policy.get("confidence", None)

    principles_text = "\n".join(
        f"- {p['text']}" for p in principles
    )

    prompt = f"""
You are explaining a strategic decision made by an AI agent.

Observed strategic state:
- Friendly strength: {friendly}
- Enemy pressure: {pressure}
- Objective distance: {objective}

Selected strategic option:
- Option: {option}
- Category: {category}
- Estimated value: {value}
- Policy confidence: {confidence}

Relevant strategic principles:
{principles_text}

Instructions:
- Explain why the selected option is coherent with the observed state.
- Use ONLY the strategic principles provided.
- Do NOT invent new principles, rules, or doctrines.
- Do NOT explain, reference, or imply any alternative options.
- Focus ONLY on the selected option.
- Describe the expected outcome in absolute terms, not relative or comparative ones.
- Do NOT discuss risks, drawbacks, costs, or trade-offs.

Clarifications about FLANK (if applicable):
- FLANK does NOT imply avoiding combat.
- FLANK represents maneuver to gain positional advantage.
- FLANK may still include limited or opportunistic attacks.
- Do NOT describe flanking as retreat, withdrawal, disengagement, or evasion.

Produce a clear, human-readable explanation.
""".strip()

    return prompt