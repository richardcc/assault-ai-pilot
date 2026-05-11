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

    confidence = policy.get("confidence")
    value = policy.get("value_estimate")

    parts = []

    # 1. State evaluation
    parts.append(
        f"The AI assessed the battlefield with friendly strength rated as {friendly} "
        f"and enemy pressure rated as {pressure}."
    )

    if objective != "UNKNOWN":
        parts.append(f"The distance to the mission objective was {objective.lower()}.")
    else:
        parts.append("The distance to the objective was not a decisive factor.")

    # 2. Option rationale
    if option == "ATTACK":
        parts.append(
            "Given the assessed pressure and available friendly strength, "
            "direct engagement was considered strategically viable."
        )

    elif option == "HOLD":
        parts.append(
            "Maintaining the current defensive posture was considered the safest option."
        )

    elif option == "FLANK":
        parts.append(
            "The AI preferred maneuver in order to improve positional advantage before engaging."
        )

    # 3. Value-based justification
    if value is not None:
        parts.append(
            f"The selected option had an estimated strategic value of {value:.2f}, "
            "suggesting a favorable expected outcome compared to alternatives."
        )

    if confidence is not None:
        parts.append(
            f"The policy confidence for this decision was {confidence:.2f}, "
            "indicating moderate certainty."
        )

    return " ".join(parts)