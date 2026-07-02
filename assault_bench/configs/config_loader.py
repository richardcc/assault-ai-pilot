from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class BenchmarkConfig:
    raw: Dict[str, Any]

    @property
    def paths(self) -> Dict[str, Any]:
        return self.raw["paths"]

    @property
    def benchmark(self) -> Dict[str, Any]:
        return self.raw["benchmark"]


def load_benchmark_config(path: Path) -> BenchmarkConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return BenchmarkConfig(raw=raw)
