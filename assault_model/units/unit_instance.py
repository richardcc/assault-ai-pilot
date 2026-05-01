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
        position: tuple[int, int] | None,
        experience: str = "REGULAR",
        event_bus=None,   # ✅ optional, injected from GameState/Runtime
    ):
        self.unit_id = unit_id
        self.unit_type = unit_type
        self.side = side
        self.position = position
        self.experience = experience

        # Event bus (may be None)
        self._event_bus = event_bus

        # ============================
        # Runtime combat state
        # ============================
        self.max_strength = unit_type.max_strength
        self.strength = self.max_strength
        self.alive = True

        # ============================
        # Transport / embark state
        # ============================
        self.embarked: bool = False
        self.carrier_id: str | None = None

        # Only meaningful for vehicles
        if self.unit_type.category.name == "VEHICLE":
            self.passengers: list[str] = []

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

    def is_embarked(self) -> bool:
        return self.embarked

    # ----------------------------
    # Movement
    # ----------------------------
    def move_to(self, q: int, r: int):
        if self.embarked:
            raise RuntimeError(
                f"Embarked unit {self.unit_id} cannot move on map"
            )
        self.position = (q, r)

    # ----------------------------
    # Embark / disembark hooks
    # ----------------------------
    def embark_into(self, vehicle: "UnitInstance"):
        if self.embarked:
            raise RuntimeError(f"{self.unit_id} already embarked")

        self.embarked = True
        self.carrier_id = vehicle.unit_id
        self.position = None
        vehicle.passengers.append(self.unit_id)

        _trace("EMBARK", unit=self.unit_id, vehicle=vehicle.unit_id)

    def disembark_from(self, vehicle: "UnitInstance", q: int, r: int):
        if not self.embarked or self.carrier_id != vehicle.unit_id:
            raise RuntimeError(f"{self.unit_id} not embarked in {vehicle.unit_id}")

        self.embarked = False
        self.carrier_id = None
        self.position = (q, r)
        vehicle.passengers.remove(self.unit_id)

        _trace("DISEMBARK", unit=self.unit_id, vehicle=vehicle.unit_id)

    # ----------------------------
    # Combat hooks
    # ----------------------------
    def apply_damage(self, dmg: int):
        if dmg <= 0 or not self.alive:
            return

        hp_before = self.strength
        self.strength -= dmg

        killed = False
        if self.strength <= 0:
            self.strength = 0
            self.alive = False
            killed = True

        hp_after = self.strength

        _trace(
            "DAMAGE_APPLIED",
            unit=self.unit_id,
            dmg=dmg,
            hp_before=hp_before,
            hp_after=hp_after,
            killed=killed,
        )

        # ✅ EMIT RAW EVENT TO BUS
        if self._event_bus:
            self._event_bus.emit(
                {
                    "type": "DIRECT_DAMAGE",
                    "payload": {
                        "target": self.unit_id,
                        "side": self.side,
                        "damage": dmg,
                        "hp_before": hp_before,
                        "hp_after": hp_after,
                        "killed": killed,
                        "position": self.position,
                        "reason": "direct_damage",
                    },
                }
            )

    def apply_suppression(self):
        # Placeholder – suppression state handled elsewhere
        pass