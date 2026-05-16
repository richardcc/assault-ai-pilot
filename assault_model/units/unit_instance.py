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

    ✅ Includes:
    - health / alive state
    - suppression system
    - fallback system
    - embark / transport logic
    ✅ NEW:
    - unified combat interface (supports DIRECT + INDIRECT fire)
    """

    def __init__(
        self,
        unit_id: str,
        unit_type: UnitType,
        side: str,
        position: tuple[int, int] | None,
        experience: str = "REGULAR",
        event_bus=None,
    ):
        self.unit_id = unit_id
        self.unit_type = unit_type
        self.side = side
        self.position = position
        self.experience = experience

        # Event bus (optional)
        self._event_bus = event_bus

        # ============================
        # Runtime combat state
        # ============================
        self.max_strength = unit_type.max_strength
        self.strength = self.max_strength
        self.alive = True

        # ============================
        # Morale state
        # ============================
        self.suppressed: bool = False
        self.fallback: bool = False

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

    def is_suppressed(self) -> bool:
        return self.suppressed

    def is_in_fallback(self) -> bool:
        return self.fallback

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
    # Distance helper ✅ NEW
    # ----------------------------
    def get_distance_to(self, other: "UnitInstance") -> int:
        if self.position is None or other.position is None:
            return 999

        q1, r1 = self.position
        q2, r2 = other.position

        return abs(q1 - q2) + abs(r1 - r2)

    # ----------------------------
    # Combat API ✅ NEW
    # ----------------------------
    def get_attack_dice(self, target: "UnitInstance"):
        """
        Resolve attack dice using UnitType logic.

        ✅ Supports:
        - DIRECT_FIRE
        - INDIRECT_FIRE
        """

        if not self.alive or target is None:
            return []

        # Cannot attack without valid positions
        if self.position is None or target.position is None:
            return []

        distance = self.get_distance_to(target)

        dice = self.unit_type.get_attack_dice(
            distance=distance,
            target_category=target.unit_type.category,
        )

        _trace(
            "ATTACK_RESOLVE",
            attacker=self.unit_id,
            target=target.unit_id,
            dist=distance,
            dice=[d.name for d in dice] if dice else [],
        )

        return dice

    # ----------------------------
    # Embark / disembark
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
            raise RuntimeError(
                f"{self.unit_id} not embarked in {vehicle.unit_id}"
            )

        self.embarked = False
        self.carrier_id = None
        self.position = (q, r)

        if hasattr(vehicle, "passengers") and self.unit_id in vehicle.passengers:
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
                    },
                }
            )

    # ----------------------------
    # Suppression
    # ----------------------------
    def apply_suppression(self):

        if not self.alive:
            return

        if self.suppressed:
            self.trigger_fallback()
            return

        self.suppressed = True

        _trace("SUPPRESSION_APPLIED", unit=self.unit_id)

        if self._event_bus:
            self._event_bus.emit(
                {
                    "type": "SUPPRESSED",
                    "payload": {
                        "unit": self.unit_id,
                        "position": self.position,
                    },
                }
            )

    def clear_suppression(self):

        if not self.suppressed:
            return

        self.suppressed = False

        _trace("SUPPRESSION_CLEARED", unit=self.unit_id)

    # ----------------------------
    # Fallback
    # ----------------------------
    def trigger_fallback(self):

        if not self.alive:
            return

        self.suppressed = False
        self.fallback = True

        _trace("FALLBACK_TRIGGERED", unit=self.unit_id)

        if self._event_bus:
            self._event_bus.emit(
                {
                    "type": "FALLBACK",
                    "payload": {
                        "unit": self.unit_id,
                        "position": self.position,
                    },
                }
            )

        if self.unit_type.category.name == "ARTILLERY":
            self.alive = False

    def clear_fallback(self):

        if not self.fallback:
            return

        self.fallback = False

        _trace("FALLBACK_CLEARED", unit=self.unit_id)