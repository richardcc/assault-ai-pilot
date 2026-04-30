# assault/core/rationale.py

from enum import Enum


class Rationale(Enum):
    """
    Canonical tactical rationales.

    These represent high-level intentions inferred from
    agent behaviour. They are NOT internal thoughts
    of the agent, but semantic categories used for
    post-hoc explanation or for training an auxiliary
    explanation head.

    This taxonomy is shared across engine, runner
    and web viewer.
    """

    ADVANCE = 0
    """
    The agent moved to reduce distance to an enemy or
    to apply forward pressure / gain ground.
    """

    HOLD = 1
    """
    The agent maintained a tactically favourable
    position.
    """

    RETREAT = 2
    """
    The agent moved to increase distance from a threat
    or to reduce exposure.
    """

    REPOSITION = 3
    """
    The agent moved laterally or structurally without
    a clear advance or retreat, adjusting formation
    or angle.
    """

    WAIT = 4
    """
    The agent did not move and did not meaningfully
    change its tactical stance.
    """
