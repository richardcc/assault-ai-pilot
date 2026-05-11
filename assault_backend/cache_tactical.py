import json
import hashlib


class TacticalCache:
    """
    Cache for tactical explanations.

    Keyed by a stable hash of activation events.
    """

    def __init__(self):
        self._cache = {}

    def _hash_events(self, events):
        """
        Create a deterministic hash from activation events.
        """
        serialized = json.dumps(events, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def make_key(self, unit_id, events):
        """
        Tactical identity = unit + exact events.
        """
        return (
            unit_id,
            self._hash_events(events),
        )

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        self._cache[key] = value

    def clear(self):
        self._cache.clear()