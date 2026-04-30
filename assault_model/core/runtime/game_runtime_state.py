from assault_model.core.game_state import GameState
from assault_model.core.turn import TurnState
from assault_model.core.activation import ActivationState


class RuntimeGameState:
    def __init__(self, base_state: GameState):
        self.base_state = base_state
        self.turn = TurnState(turn_number=base_state.turn)
        self.activation = ActivationState(base_state.units)
