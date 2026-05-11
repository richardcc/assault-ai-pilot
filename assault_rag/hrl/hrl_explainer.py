from typing import Dict

def explain_hrl_decision(event: Dict) -> str:
    """
    Generate a strategic explanation for a HRL_DECISION event.
    """

    option = event["option"]
    category = event["category"]
    ctx = event.get("context", {})
    policy = event.get("policy_info", {})

    friendly = ctx.get("friendly_strength", "UNKNOWN")
    pressure = ctx.get("enemy_pressure", "UNKNOWN")
    objective = ctx.get("objective_distance", "UNKNOWN")

    confidence = policy.get("confidence", None)
    value = policy.get("value_estimate", None)

    lines = []

    # 1. Describe perceived state
    lines.append(
        f"The AI evaluated the battlefield with friendly strength assessed as {friendly} "
        f"and enemy pressure assessed as {pressure}."
    )

    if objective != "UNKNOWN":
        lines.append(f"The objective distance was assessed as {objective}.")
    else:
        lines.append("The distance to the objective was not a dominant factor in this decision.")

    # 2. Explain option choice
    if option == "ATTACK":
        lines.append(
            "Given the current pressure and sufficient friendly strength, engaging the enemy "
            "directly was evaluated as a viable strategic option."
        )

    elif option == "HOLD":
        lines.append(
            "The AI determined that maintaining current positions would minimize risk under pressure."
        )

    elif option == "FLANK":
        lines.append(
            "The AI favored maneuver over direct engagement, aiming to improve positional advantage."
        )

    # 3. Explain value-based selection
    if value is not None:
        lines.append(
            f"The selected option had an estimated strategic value of {value:.2f}, "
            "indicating a favorable expected outcome compared to alternatives."
        )

    if confidence is not None:
        lines.append(
            f"The policy confidence for this decision was {confidence:.2f}, "
            "showing moderate certainty in the chosen course of action."
        )

    return " ".join(lines)