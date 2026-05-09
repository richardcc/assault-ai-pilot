import json


def _json_default(obj):
    """
    Fallback JSON serializer for non-serializable objects.
    """
    # HexCoord -> {q, r}
    if hasattr(obj, "q") and hasattr(obj, "r"):
        return {"q": obj.q, "r": obj.r}

    # Enum -> value
    if hasattr(obj, "value"):
        return obj.value

    # Fallback to string
    return str(obj)


class ReplayWriter:
    """
    Responsible only for persisting a Replay to disk.
    """

    @staticmethod
    def write(replay, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                replay.to_dict(),
                f,
                indent=2,
                default=_json_default,
            )