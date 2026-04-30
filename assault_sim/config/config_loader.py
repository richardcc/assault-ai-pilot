# assault_sim/config/config_loader.py
#
# Simulation configuration loader.
#
# Responsibilities:
# - load the YAML file
# - keep configuration sections separated
# - build DebugConfig OUTSIDE of DebugConfig itself
#
# DebugConfig is intentionally a simple dataclass.
# Mapping from YAML -> DebugConfig happens ONLY here.

from pathlib import Path
import yaml

from assault_sim.debug.debug_config import DebugConfig


class SimConfig:
    """
    High-level simulation configuration container.

    Responsibilities:
    - store raw YAML
    - expose paths and scenario selection
    - expose DebugConfig built from YAML
    """

    def __init__(self, raw: dict):
        # Keep raw config
        self.raw = raw

        # -------------------------------
        # Data paths
        # -------------------------------
        self.data_root = Path(raw["data_root"])
        self.unit_catalog = raw["catalogs"]["unit_catalog"]
        self.map_piece_catalog = raw["catalogs"]["map_piece_catalog"]
        self.scenario_folder = raw["catalogs"]["scenario_folder"]

        # -------------------------------
        # Scenario
        # -------------------------------
        self.scenario_name = raw["scenario"]["name"]

        # -------------------------------
        # Observability -> DebugConfig
        # -------------------------------
        self.debug = build_debug_config(
            raw.get("observability", {})
        )


def build_debug_config(obs: dict) -> DebugConfig:
    """
    Build DebugConfig from 'observability' YAML section.

    IMPORTANT:
    DebugConfig only supports:
      - enabled
      - log_actions
      - log_turns
      - log_vp

    Anything else stays outside DebugConfig
    (movement, effects, close combat, etc.).
    """

    if not obs or not obs.get("enabled", False):
        return DebugConfig(enabled=False)

    events = obs.get("events", {})

    return DebugConfig(
        enabled=True,
        log_actions=events.get("actions", False),
        log_turns=events.get("turns", False),
        log_vp=events.get("victory", False),
    )


def load_sim_config(path: Path) -> SimConfig:
    """
    Load simulation configuration from YAML file.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return SimConfig(raw)