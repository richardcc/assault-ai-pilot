class HRLCache:
    """
    Cache for strategic (HRL) explanations.

    Keyed by semantic strategic state, NOT by object stringification.
    Safe to reuse across units only when state truly matches.
    """

    def __init__(self):
        self._cache = {}

    def make_key(self, unit_id, action, strategic_state):
        """
        Build a stable semantic cache key for HRL.
        """
        return (
            unit_id,
            action,
            strategic_state.friendly_strength,
            strategic_state.enemy_pressure,
            strategic_state.objective_distance,
        )

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        self._cache[key] = value

    def clear(self):
        self._cache.clear()