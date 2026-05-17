import torch
import torch.nn as nn
import torch.nn.functional as F


class PolicyNet(nn.Module):
    """
    PPO Policy Network with dual decision heads + LSTM memory.
    """

    def __init__(self, input_dim: int, num_options: int):
        super().__init__()

        self.hidden_size = 128

        # -------------------------------------------------
        # ✅ ENCODER (tu backbone)
        # -------------------------------------------------
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
        )

        # -------------------------------------------------
        # 🔥 LSTM (NUEVO)
        # -------------------------------------------------
        self.lstm = nn.LSTM(
            input_size=128,
            hidden_size=self.hidden_size,
            batch_first=True
        )

        # -------------------------------------------------
        # ✅ OPTION HEAD
        # -------------------------------------------------
        self.option_head = nn.Linear(self.hidden_size, num_options)

        # -------------------------------------------------
        # ✅ ATTACK MODE HEAD
        # -------------------------------------------------
        self.attack_mode_head = nn.Linear(self.hidden_size, 2)

        # -------------------------------------------------
        # ✅ VALUE HEAD
        # -------------------------------------------------
        self.value_head = nn.Linear(self.hidden_size, 1)

    # -------------------------------------------------
    def forward(self, x, hidden):

        # ✅ encoder
        features = self.backbone(x)   # [B, 128]

        # ✅ LSTM espera [B, T, F]
        features = features.unsqueeze(1)  # T=1

        out, hidden = self.lstm(features, hidden)

        out = out.squeeze(1)  # [B, 128]

        option_logits = self.option_head(out)
        attack_mode_logits = self.attack_mode_head(out)
        value = self.value_head(out)

        return option_logits, attack_mode_logits, value, hidden

    # -------------------------------------------------
    def init_hidden(self, batch_size=1, device=None):

        if device is None:
            device = next(self.parameters()).device

        h = torch.zeros(1, batch_size, self.hidden_size, device=device)
        c = torch.zeros(1, batch_size, self.hidden_size, device=device)

        return (h, c)