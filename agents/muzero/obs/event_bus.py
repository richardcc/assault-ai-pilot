from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EventBus:
    events: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.events.append({"type": event_type, "payload": payload})
