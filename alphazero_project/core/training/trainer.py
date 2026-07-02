import torch
import torch.nn.functional as F
import numpy as np


class Trainer:

    def __init__(self, model, lr=1e-3):
        self.model = model
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

    # -------------------------
    def train_batch(self, batch):
        """
        batch = list of {
            state: np.array (C,H,W)
            policy: list
            value: float
        }
        """

        states = []
        policies = []
        values = []

        for sample in batch:
            states.append(sample["state"])
            policies.append(sample["policy"])
            values.append(sample["value"])

        states = torch.tensor(np.array(states), dtype=torch.float32)
        policies = torch.tensor(np.array(policies), dtype=torch.float32)
        values = torch.tensor(np.array(values), dtype=torch.float32).unsqueeze(1)

        # -------------------------
        # FORWARD
        # -------------------------
        logits, pred_values = self.model(states)

        # -------------------------
        # POLICY LOSS
        # -------------------------
        log_probs = F.log_softmax(logits, dim=1)
        policy_loss = -torch.mean(torch.sum(policies * log_probs, dim=1))

        # -------------------------
        # VALUE LOSS
        # -------------------------
        value_loss = F.mse_loss(pred_values, values)

        # -------------------------
        # TOTAL LOSS
        # -------------------------
        loss = policy_loss + value_loss

        # -------------------------
        # BACKPROP
        # -------------------------
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return {
            "loss": loss.item(),
            "policy_loss": policy_loss.item(),
            "value_loss": value_loss.item()
        }