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

    def __init__(self, raw: dict, config_dir: Path | None = None):
        # Keep raw config
        self.raw = raw

        # -------------------------------
        # Data paths
        # -------------------------------
        data_root = Path(raw["data_root"])
        if data_root.is_absolute():
            self.data_root = data_root
        else:
            candidates = []
            if config_dir is not None:
                # 1) relative to config folder
                candidates.append((config_dir / data_root).resolve())
                # 2) relative to assault_sim/ (parent of config/)
                candidates.append((config_dir.parent / data_root).resolve())
                # 3) relative to repo root (parent of assault_sim/)
                candidates.append((config_dir.parent.parent / data_root).resolve())
            # 4) relative to current working directory
            candidates.append((Path.cwd() / data_root).resolve())

            existing = next((p for p in candidates if p.exists()), None)
            self.data_root = existing if existing is not None else candidates[0]
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

    return SimConfig(raw, config_dir=path.parent)