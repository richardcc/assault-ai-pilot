from assault_model.units.unit_type import UnitType
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class UnitInstance:
    """
    Runtime instance of a unit on the battlefield.
    """

    def __init__(
        self,
        unit_id: str,
        unit_type: UnitType,
        side: str,
        position: tuple[int, int],
        experience: str = "REGULAR",
    ):
        self.unit_id = unit_id
        self.unit_type = unit_type
        self.side = side
        self.position = position
        self.experience = experience

        # ============================
        # Runtime combat state
        # ============================
        self.max_strength = unit_type.max_strength
        self.strength = self.max_strength
        self.alive = True

    # ----------------------------
    # Aliases
    # ----------------------------
    @property
    def hp(self) -> int:
        return self.strength

    # ----------------------------
    # State checks
    # ----------------------------
    def is_alive(self) -> bool:
        return self.alive

    def is_eliminated(self) -> bool:
        return not self.alive

    def is_half_strength(self) -> bool:
        return self.strength <= (self.max_strength // 2)

    # ----------------------------
    # Movement
    # ----------------------------
    def move_to(self, q: int, r: int):
        self.position = (q, r)

    # ----------------------------
    # Combat hooks
    # ----------------------------
    def apply_damage(self, dmg: int):
        if dmg <= 0 or not self.alive:
            return

        self.strength -= dmg
        if self.strength <= 0:
            self.strength = 0
            self.alive = False

    def apply_suppression(self):
        # Placeholder – suppression state handled elsewhere
        pass