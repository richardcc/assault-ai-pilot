# assault_engine/adapter/model_adapter.py
from assault_model.core.game_state import GameState
from assault_model.core.game_state_runtime import RuntimeGameState


def initialize_engine_state(game_state: GameState) -> RuntimeGameState:
    return RuntimeGameState(game_state)