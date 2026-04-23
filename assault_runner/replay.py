"""
Replay: complete and neutral record of a played game.

Designed for:
- Viewer / Debugger
- Evaluation
- Persistence / logging
- Offline consumption (training, analysis)

Does NOT contain:
- rewards
- gradients
- learning logic
"""

from dataclasses import dataclass
from typing import List, Any


@dataclass(frozen=True)
class Replay:
    """
    Immutable replay of a full game.
    Stores the ordered sequence of game states.
    """
    initial_state: Any
    states: List[Any]
    final_state: Any

    def __len__(self) -> int:
        return len(self.states)

    def get_state(self, index: int) -> Any:
        return self.states[index]
