from alphazero_project.core.interfaces import GameInterface


class AssaultModelAdapter(GameInterface):

    def __init__(self, sim):
        self.sim = sim

    # ✅ estado inicial (muy importante)
    def get_initial_state(self):
        return self.sim.get_initial_state()

    # ✅ acciones legales
    def get_legal_actions(self, state):
        return self.sim.get_legal_actions(state)

    # ✅ transición
    def step(self, state, action):
        return self.sim.step(state, action)

    # ✅ terminal (interfaz estándar)
    def is_terminal(self, state):
        return self.sim.is_done(state)
