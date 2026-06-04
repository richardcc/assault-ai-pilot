import torch
import torch.nn as nn


class PolicyNet(nn.Module):

    def __init__(self, input_dim: int, num_options: int):
        super().__init__()

        self.hidden_size = 128

        # Backbone
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
        )

        # LSTM
        self.lstm = nn.LSTM(
            input_size=128,
            hidden_size=self.hidden_size,
            batch_first=True
        )

        # Heads
        self.option_head = nn.Linear(self.hidden_size, num_options)
        self.attack_mode_head = nn.Linear(self.hidden_size, 2)
        self.value_head = nn.Linear(self.hidden_size, 1)

    # -------------------------------------------------
    def forward(self, x, hidden=None):

        # ✅ asegurar tensor
        if not isinstance(x, torch.Tensor):
            x = torch.tensor(x, dtype=torch.float32)

        if x.dim() == 1:
            x = x.unsqueeze(0)

        # ✅ hidden init
        if x.dim() == 2:
            batch_size = x.shape[0]
        elif x.dim() == 3:
            batch_size = x.shape[0]
        else:
            raise ValueError(f"Unsupported input rank for PolicyNet: {x.dim()}")

        if hidden is None:
            hidden = self.init_hidden(batch_size, device=x.device)

        # encoder
        if x.dim() == 2:
            features = self.backbone(x)
            features = features.unsqueeze(1)  # [B, 1, F]
            squeeze_time = True
        else:
            b, t, f = x.shape
            features = self.backbone(x.reshape(b * t, f)).reshape(b, t, -1)
            squeeze_time = False

        out, hidden = self.lstm(features, hidden)
        option_logits = self.option_head(out)
        attack_mode_logits = self.attack_mode_head(out)
        value = self.value_head(out).squeeze(-1)

        if squeeze_time:
            option_logits = option_logits.squeeze(1)
            attack_mode_logits = attack_mode_logits.squeeze(1)
            value = value.squeeze(1)

        return option_logits, attack_mode_logits, value, hidden

    # -------------------------------------------------
    def init_hidden(self, batch_size=1, device=None):

        if device is None:
            device = next(self.parameters()).device

        h = torch.zeros(1, batch_size, self.hidden_size, device=device)
        c = torch.zeros(1, batch_size, self.hidden_size, device=device)

        return (h, c)