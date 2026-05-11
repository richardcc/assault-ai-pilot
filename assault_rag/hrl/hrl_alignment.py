def find_relevant_hrl_decision(turn_events: list, action_index: int):
    """
    Find the closest HRL_DECISION that appears before
    the ACTION at action_index within the same turn.
    """
    for i in range(action_index - 1, -1, -1):
        ev = turn_events[i]
        if ev["type"] == "HRL_DECISION":
            return ev["payload"]
    return None