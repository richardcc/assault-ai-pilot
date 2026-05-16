class Strategy:
    """
    Declarative preference profile.
    Contract:
    - weigh(areas: dict) -> dict[str, float]
    """
    def weigh(self, areas: dict) -> dict:
        raise NotImplementedError
