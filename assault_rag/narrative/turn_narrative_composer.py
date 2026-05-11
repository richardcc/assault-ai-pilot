from typing import List

def compose_turn_narrative(
    turn: int,
    hrl_explanation: str,
    tactical_explanations: List[str]
) -> str:
    """
    Compose a unified narrative for a single turn,
    combining strategic intent and tactical execution.
    """

    narrative = []

    narrative.append(f"Turn {turn} – Strategic Intent:")
    narrative.append(hrl_explanation.strip())

    narrative.append("\nTactical Execution:")

    for idx, tact_exp in enumerate(tactical_explanations, start=1):
        narrative.append(f"{idx}. {tact_exp.strip()}")

    return "\n".join(narrative)