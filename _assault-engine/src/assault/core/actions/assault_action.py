from dataclasses import dataclass


@dataclass(frozen=True)
class AssaultAction:
    """
    Declarative assault action.

    This action contains no logic.
    Resolution is handled exclusively by:
    - AssaultExecutor (orchestration + effects)
    - AssaultResolver (pure combat logic)
    """