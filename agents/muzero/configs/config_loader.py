from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class MuZeroConfig:
    raw: Dict[str, Any]

    @property
    def paths(self) -> Dict[str, Any]:
        return self.raw["paths"]

    @property
    def scenario(self) -> Dict[str, Any]:
        return self.raw["scenario"]

    @property
    def model(self) -> Dict[str, Any]:
        return self.raw["model"]

    @property
    def selfplay(self) -> Dict[str, Any]:
        return self.raw["selfplay"]

    @property
    def train(self) -> Dict[str, Any]:
        return self.raw["train"]


def load_muzero_config(path: Path) -> MuZeroConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return MuZeroConfig(raw=raw)
