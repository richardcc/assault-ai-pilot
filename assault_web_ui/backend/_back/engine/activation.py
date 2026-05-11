from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Activation:
    unit_id: str
    action: str
    events: List[Dict]
    context: Dict[str, Any]


def extract_activation(replay: Dict, turn: int, step: int) -> Activation:
    """
    turn, step are 1-based (UI)
    """
    turn_idx = turn - 1
    step_idx = step - 1

    turn_data = replay["turns"][turn_idx]
    events = turn_data["events"]

    action_event = events[step_idx]
    if action_event["type"] != "ACTION":
        raise ValueError("Step does not point to an ACTION")

    unit_id = action_event["payload"]["active_unit"]
    action = action_event["payload"]["action"]

    activation_events = [action_event]

    i = step_idx + 1
    while i < len(events) and events[i]["type"] != "ACTION":
        activation_events.append(events[i])
        i += 1

    # Strategic context (VERY IMPORTANT)
    context = {
        "side": unit_id.split("_")[0],
        "turn": turn,
        "friendly_strength": "EVEN",
        "enemy_pressure": "HIGH",
        "objective_distance": "UNKNOWN",
    }

    return Activation(
        unit_id=unit_id,
        action=action,
        events=activation_events,
        context=context,
    )