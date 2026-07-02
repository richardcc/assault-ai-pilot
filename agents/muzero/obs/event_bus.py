from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EventBus:
    events: List[Dict[str, Any]] = field(default_factory=list)

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append({"type": event_type, "payload": payload})
