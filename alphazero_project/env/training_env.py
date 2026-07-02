from alphazero_project.core.planner.plan_context import PlanContext
from alphazero_project.core.decision.decision import decide
from alphazero_project.core.telemetry.logger import log


class TrainingEnv:

    def __init__(self, game, config):
        self.game = game
        self.config = config
        self.state = None

    # -------------------------
    def reset(self, state):
        self.state = state

    # -------------------------
    def step(self):
        plan = PlanContext()

        action_idx, out = decide(self.state, plan, self.game, self.config)

        legal_actions = self.game.get_legal_actions(self.state)

        if not legal_actions:
            raise RuntimeError("No legal actions available")

        action_idx = min(action_idx, len(legal_actions) - 1)
        action = legal_actions[action_idx]

        # 🔥 PRINT CLAVE
        print("\n========================")
        print(f"TURN STATE ID: {id(self.state)}")

        # 👉 intenta mostrar turno si existe
        turn = getattr(self.state, "turn", "UNKNOWN")
        print(f"TURN: {turn}")

        print(f"ACTION CHOSEN: {action}")
        print(f"VALUE: {out['value']:.4f}")

        # 👉 mostrar top-3 acciones más probables
        policy = out["policy"]
        top_indices = sorted(range(len(policy)), key=lambda i: policy[i], reverse=True)[:3]

        print("TOP ACTIONS:")
        for i in top_indices:
            print(f"  idx={i}, prob={policy[i]:.3f}, action={legal_actions[i]}")

        self.state = self.game.step(self.state, action)

        return self.state