from alphazero_project.core.mcts.mcts import MCTS
from alphazero_project.core.model.model import forward


def decide(state, plan, game, config):
    # -------------------------
    # INICIALIZAR MCTS
    # -------------------------
    mcts = MCTS(
        game=game,
        config=config,
        model_forward=forward,
        num_simulations=30
    )

    # -------------------------
    # EJECUTAR
    # -------------------------
    action_idx, out = mcts.run(state)

    return action_idx, out