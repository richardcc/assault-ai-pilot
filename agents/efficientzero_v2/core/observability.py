from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import orjson


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
        with self.path.open("ab") as f:
            f.write(orjson.dumps(event) + b"\n")


@dataclass
class RunManifest:
    run_id: str
    scenario_id: str
    seed: int
    config: dict[str, Any]

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(orjson.dumps(asdict(self), option=orjson.OPT_INDENT_2))
