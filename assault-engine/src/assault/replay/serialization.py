import json


def replay_to_dict(replay: dict) -> dict:
    """
    Convert a replay structure to a JSON-serializable dict.

    NEW CONTRACT:
    - 'replay' is already a dict produced by GameSession
    - It contains:
        {
          "scenario": str,
          "frames": list[dict],
          "outcome": dict
        }
    - All frames MUST already be JSON-safe
    - This function performs NO transformation, only validation
    """

    if not isinstance(replay, dict):
        raise TypeError(f"Replay must be a dict, got {type(replay)}")

    if "frames" not in replay:
        raise ValueError("Replay dict missing 'frames'")

    if not isinstance(replay["frames"], list):
        raise TypeError("Replay 'frames' must be a list")

    # Minimal validation of frames
    for i, frame in enumerate(replay["frames"]):
        if not isinstance(frame, dict):
            raise TypeError(f"Frame {i} is not a dict")

        if "round" not in frame:
            raise ValueError(f"Frame {i} missing 'round'")

        # Either action frame or event frame
        if "action" not in frame and "event" not in frame:
            raise ValueError(
                f"Frame {i} must contain either 'action' or 'event'"
            )

    return replay


def save_replay_to_json(replay: dict, file_path: str) -> None:
    """
    Save replay dict to a JSON file.

    This function assumes replay is already fully JSON-serializable.
    """

    data = replay_to_dict(replay)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)