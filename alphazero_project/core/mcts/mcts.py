import numpy as np


# =====================================================
# NODE
# =====================================================

class MCTSNode:

    def __init__(self, state, parent=None, prior=0.0):
        self.state = state
        self.parent = parent
        self.prior = prior

        self.children = {}  # action -> node

        self.visits = 0
        self.value_sum = 0.0

    # -------------------------
    def value(self):
        if self.visits == 0:
            return 0.0
        return self.value_sum / self.visits

    # -------------------------
    def is_expanded(self):
        return len(self.children) > 0


# =====================================================
# MCTS
# =====================================================

class MCTS:

    def __init__(self, game, config, model_forward,
                 num_simulations=30, c_puct=1.4):

        self.game = game
        self.config = config
        self.forward = model_forward

        self.num_simulations = num_simulations
        self.c_puct = c_puct

    # =====================================================
    # MAIN ENTRY
    # =====================================================
    def run(self, root_state):
        root = MCTSNode(root_state)

        # ✅ expand root
        self.expand(root)

        for _ in range(self.num_simulations):
            node = root
            path = [node]

            # -------------------------
            # SELECT
            # -------------------------
            while node.is_expanded():
                action, node = self.select(node)
                path.append(node)

            # -------------------------
            # EVALUATE
            # -------------------------
            value = self.evaluate(node)

            # -------------------------
            # EXPAND
            # -------------------------
            if not self.game.is_terminal(node.state):
                self.expand(node)

            # -------------------------
            # BACKPROP
            # -------------------------
            self.backpropagate(path, value)

        # -------------------------
        # FINAL POLICY (visits)
        # -------------------------
        actions = list(root.children.keys())

        visits = np.array(
            [child.visits for child in root.children.values()],
            dtype=np.float32
        )

        if visits.sum() > 0:
            probs = visits / visits.sum()
        else:
            probs = np.ones(len(actions)) / len(actions)

        best_idx = int(np.argmax(probs))

        # ✅ devolver ÍNDICE (NO acción)
        return best_idx, {
            "policy": probs.tolist(),
            "value": root.value()
        }

    # =====================================================
    # SELECT (UCB)
    # =====================================================
    def select(self, node):
        best_score = -np.inf
        best_action = None
        best_child = None

        total_visits = sum(child.visits for child in node.children.values()) + 1

        for action, child in node.children.items():

            q = child.value()

            u = self.c_puct * child.prior * np.sqrt(total_visits) / (1 + child.visits)

            score = q + u

            if score > best_score:
                best_score = score
                best_action = action
                best_child = child

        return best_action, best_child

    # =====================================================
    # EXPAND
    # =====================================================
    def expand(self, node):
        legal_actions = self.game.get_legal_actions(node.state)

        if not legal_actions:
            return

        x = self.encode(node.state)
        out = self.forward(x)

        policy = np.array(out["policy"], dtype=np.float32)
        policy = policy[:len(legal_actions)]

        if policy.sum() > 0:
            policy /= policy.sum()
        else:
            policy = np.ones(len(legal_actions)) / len(legal_actions)

        for action, p in zip(legal_actions, policy):
            next_state = self.game.step(node.state, action)

            node.children[action] = MCTSNode(
                state=next_state,
                parent=node,
                prior=float(p)
            )

    # =====================================================
    # EVALUATE
    # =====================================================
    def evaluate(self, node):
        if self.game.is_terminal(node.state):
            return 0.0

        x = self.encode(node.state)
        out = self.forward(x)

        return float(out["value"])

    # =====================================================
    # BACKPROP
    # =====================================================
    def backpropagate(self, path, value):
        for node in reversed(path):
            node.visits += 1
            node.value_sum += value

    # =====================================================
    # ENCODER BRIDGE
    # =====================================================
    def encode(self, state):
        from alphazero_project.core.encoder.encoder import encode_state
        return encode_state(state, self.config)