class KnowledgeBrick:
    """
    Atomic knowledge unit.
    Contract:
    - evaluate(state, unit_id, context=None) -> dict
    - pure (no state, no side effects)
    """
    def evaluate(self, state, unit_id, context=None) -> dict:
        raise NotImplementedError
