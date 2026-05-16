class StrategyRegistry:
    def __init__(self):
        self._strategies = {}

    def register(self, name: str, strategy):
        self._strategies[name] = strategy

    def get(self, name: str):
        return self._strategies[name]
