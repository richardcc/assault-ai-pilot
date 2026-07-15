from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EventBus:
    events: list[dict[str, Any]] = field(default_factory=list)
    enabled: bool = True

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.events.append({"type": event_type, "payload": payload})


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")


@dataclass
class RunManifest:
    run_id: str
    scenario_id: str
    seed: int
    config: dict[str, Any]

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

