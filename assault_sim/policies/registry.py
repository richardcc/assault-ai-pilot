class PolicyRegistry:
    def __init__(self):
        self._policies = {}

    def register(self, name: str, policy):
        self._policies[name] = policy

    def resolve(self, name: str):
        return self._policies[name]