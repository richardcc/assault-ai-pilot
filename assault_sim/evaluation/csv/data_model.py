from dataclasses import dataclass
from typing import Optional

# -------------------------------------------------
# EXPERIMENT
# -------------------------------------------------

@dataclass
class ExperimentRow:
    experiment_id: str
    model_type: str
    opponent: str
    scenario: str
    seed: int
    num_episodes: int


# -------------------------------------------------
# EPISODE (MACRO)
# -------------------------------------------------

@dataclass
class EpisodeRow:
    experiment_id: str
    episode_id: int
    winner: str
    final_vp: int
    steps: int
    rl_damage: int
    enemy_damage: int


# -------------------------------------------------
# DECISION (🔥 CORE)
# -------------------------------------------------

@dataclass
class DecisionRow:
    experiment_id: str
    episode_id: int
    turn: int
    unit_id: str

    # HRL
    l3_strategy: str
    l2_option: str
    attack_mode: Optional[str]

    # Model confidence
    confidence: float
    value_estimate: float

    # Context
    enemy_distance: Optional[int]
    terrain: Optional[str]
    hp: int


# -------------------------------------------------
# OUTCOME (L1)
# -------------------------------------------------

@dataclass
class OutcomeRow:
    experiment_id: str
    episode_id: int
    turn: int
    unit_id: str

    action: str
    result: str
    damage: int
    kills: int
    unit_alive_after: bool
