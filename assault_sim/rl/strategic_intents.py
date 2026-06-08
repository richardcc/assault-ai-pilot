from enum import Enum


class StrategicIntent(Enum):
    """
    L3 strategy layer.
    """

    CAPTURE = 0   # Capture objectives / VP hexes
    DENY = 1      # Deny enemy objective capture
    ATTRIT = 2    # Maximize enemy damage / removals
    PRESERVE = 3  # Preserve force and avoid bad trades

    def description(self) -> str:
        return {
            StrategicIntent.CAPTURE: "capture objectives",
            StrategicIntent.DENY: "deny enemy objective progress",
            StrategicIntent.ATTRIT: "attrit enemy combat power",
            StrategicIntent.PRESERVE: "preserve own force",
        }[self]
