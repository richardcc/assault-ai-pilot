def explain_activation(
    activation: dict,
    hrl_explanation: str,
    tactical_explanation: str
) -> dict:
    """
    Build a full explanation object for one activation.
    """

    return {
        "unit": activation["unit"],
        "action": activation["action"],
        "strategic_intent": hrl_explanation,
        "tactical_execution": tactical_explanation,
    }