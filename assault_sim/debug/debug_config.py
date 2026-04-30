from dataclasses import dataclass
@dataclass
class DebugConfig:
    enabled: bool = False
    log_actions: bool = False
    log_turns: bool = False
    log_vp: bool = False
