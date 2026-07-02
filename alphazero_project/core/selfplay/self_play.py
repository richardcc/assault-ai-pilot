from alphazero_project.core.mcts.mcts import MCTS
from alphazero_project.core.model.model import forward
from alphazero_project.core.encoder.encoder import encode_state


class SelfPlay:

    def __init__(self, game, config):
        self.game = game
        self.config = config

        self.mcts = MCTS(
            game=game,
            config=config,
            model_forward=forward,
            num_simulations=30
        )

    # -------------------------
    def play_episode(self):
        state = self.game.get_initial_state()

        episode = []

        done = False

        step_count = 0
        max_steps = 50


        while not done  and step_count < max_steps: 

            step_count += 1
            print(f"[SELF-PLAY] step {step_count}")
            # -------------------------
            # MCTS
            # -------------------------
            action_idx, out = self.mcts.run(state)

            # -------------------------
            # ENCODE
            # -------------------------
            x = encode_state(state, self.config)

            # -------------------------
            # STORE
            # -------------------------
            episode.append({
                "state": x,
                "policy": out["policy"]
            })

            # -------------------------
            # STEP
            # -------------------------
            legal_actions = self.game.get_legal_actions(state)

            if not legal_actions:
                raise RuntimeError("No legal actions")

            action = legal_actions[action_idx]

            # 🔥 DEBUG: VER DECISIÓN
            print("\n========================")

            turn = getattr(state, "turn", "UNKNOWN")
            print(f"TURN: {turn}")

            print(f"ACTION CHOSEN: {action}")
            print(f"VALUE: {out['value']:.4f}")

            policy = out["policy"]

            top_indices = sorted(
                range(len(policy)),
                key=lambda i: policy[i],
                reverse=True
            )[:3]

            print("TOP ACTIONS:")
            for i in top_indices:
                print(f"  idx={i}, prob={policy[i]:.3f}, action={legal_actions[i]}")

            # -------------------------
            # APLICAR ACCIÓN
            # -------------------------
            state = self.game.step(state, action)

            next_turn = getattr(state, "turn", "UNKNOWN")
            print(f"NEXT TURN: {next_turn}")

        # -------------------------
        # RESULTADO FINAL
        # -------------------------
        value = self.compute_outcome(state)

        for step in episode:
            step["value"] = value

        return episode

    # -------------------------
    def compute_outcome(self, state):
        """
        +1 = win
        0 = draw
        -1 = loss
        """

        # ⚠️ placeholder (puedes mejorar luego)
        if hasattr(state, "winner"):
            if state.winner == state.turn:
                return 1.0
            else:
                return -1.0

        return 0.0