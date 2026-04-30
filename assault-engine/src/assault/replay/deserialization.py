def replay_from_dict(data: dict) -> dict:
    """
    Load a replay dict from JSON into memory.

    NEW CONTRACT:
    - The replay is already a fully-serialized dict.
    - Structure:
        {
          "scenario": str,
          "frames": list[dict],
          "outcome": dict
        }
    - This function performs ONLY structural validation.
    - No game objects are reconstructed.
    """

    if not isinstance(data, dict):
        raise TypeError(f"Replay data must be a dict, got {type(data)}")

    if "frames" not in data:
        raise ValueError("Replay missing 'frames' field")

    if not isinstance(data["frames"], list):
        raise TypeError("'frames' must be a list")

    for i, frame in enumerate(data["frames"]):
        if not isinstance(frame, dict):
            raise TypeError(f"Frame {i} is not a dict")

        if "round" not in frame:
            raise ValueError(f"Frame {i} missing 'round'")

        if "action" not in frame and "event" not in frame:
            raise ValueError(
                f"Frame {i} must contain either 'action' or 'event'"
            )

        # Optional fields: unit_id, observation, reward, combat

    return data