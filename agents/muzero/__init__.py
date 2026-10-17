import warnings

warnings.warn(
    "DEPRECATION / DECOMMISSION WARNING: MuZero is fully decommissioned and obsolete in this project. "
    "All training, testing, evaluations, and experiments must exclusively use EfficientZero v2 (agents/efficientzero_v2).",
    DeprecationWarning,
    stacklevel=2,
)

from agents.muzero.adapter_voec import MuZeroVOECAdapter

__all__ = ["MuZeroVOECAdapter"]

