def explain_hrl_rag(context: dict, hrl_corpus: dict) -> dict:
    """
    Very simple HRL RAG (deterministic + text).
    """

    option = context.get("preferred_option", None)

    # Fallback logic
    if context["enemy_pressure"] == "HIGH":
        option = "FLANK"
        category = "MANEUVER"
    else:
        option = "HOLD"
        category = "DEFENSIVE"

    explanation = (
        f"The selected strategic option is {option}. "
        f"Given the observed conditions of friendly strength being "
        f"{context['friendly_strength']} and enemy pressure being "
        f"{context['enemy_pressure']}, this decision is coherent with "
        f"the strategic principles in the HRL corpus."
    )

    return {
        "option": option,
        "category": category,
        "explanation": explanation,
    }