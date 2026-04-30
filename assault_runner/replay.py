"""
Replay: complete and neutral record of a played game.

Designed for:
- Viewer / Debugger
- Evaluation
- Persistence / logging
- Offline consumption (training, analysis)

Supports:
- ACTION states (agent decisions)
- SYSTEM EVENT states (END_TURN, END_MATCH)

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

    A replay consists of an ordered sequence of states.
    Each state may represent:
      - an agent ACTION
      - a SYSTEM EVENT (e.g. END_TURN, END_MATCH)

    No assumptions are made about the internal structure
    of the stored states.
    """
    initial_state: Any
    states: List[Any]
    final_state: Any

    def __len__(self) -> int:
        return len(self.states)

    def get_state(self, index: int) -> Any:
        return self.states[index]

    # --------------------------------------------------
    # Minimal helpers for event-aware consumers
    # --------------------------------------------------

    def iter_states(self):
        """Iterate over all states in order."""
        return iter(self.states)

    def iter_events(self):
        """
        Iterate over SYSTEM EVENT states.

        Convention:
        A state is considered an event if it contains
        a key named 'event'.
        """
        for state in self.states:
            if isinstance(state, dict) and "event" in state:
                yield state

    def iter_actions(self):
        """
        Iterate over ACTION states.

        Convention:
        A state is considered an action if it contains
        a key named 'action'.
        """
        for state in self.states:
            if isinstance(state, dict) and "action" in state:
                yield state