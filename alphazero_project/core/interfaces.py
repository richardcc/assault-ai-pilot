class GameInterface:
    def get_legal_actions(self, state):
        raise NotImplementedError

    def step(self, state, action):
        raise NotImplementedError

    def is_terminal(self, state):
        raise NotImplementedError
