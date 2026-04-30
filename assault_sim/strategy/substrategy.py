class SubStrategy(Strategy):
    """
    Conditional strategy variant.
    Contract:
    - is_active(state, context) -> bool
    """
    def is_active(self, state, context=None) -> bool:
        raise NotImplementedError
