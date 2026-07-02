import torch
import torch.nn as nn
import torch.nn.functional as F


class AssaultNet(nn.Module):

    def __init__(self, in_channels=6, board_size=20, policy_size=64):
        super().__init__()

        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU()
        )

        self.flat_size = 64 * board_size * board_size

        self.policy_head = nn.Sequential(
            nn.Linear(self.flat_size, 128),
            nn.ReLU(),
            nn.Linear(128, policy_size)
        )

        self.value_head = nn.Sequential(
            nn.Linear(self.flat_size, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Tanh()
        )

    def forward(self, x):
        x = self.conv(x)
        x = x.view(x.size(0), -1)

        policy_logits = self.policy_head(x)
        value = self.value_head(x)

        return policy_logits, value


# ✅ instancia global simple
_model = AssaultNet()


def forward(x):
    x = torch.tensor(x, dtype=torch.float32).unsqueeze(0)

    logits, value = _model(x)

    policy = F.softmax(logits, dim=1).detach().cpu().numpy()[0]
    value = float(value.item())

    return {
        "policy": policy.tolist(),
        "value": value
    }
def get_model():
    return _model
