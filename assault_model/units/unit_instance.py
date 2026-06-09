from assault_model.units.unit_type import UnitType
from assault_model.map.hex_utils import safe_hex_distance
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class UnitInstance:

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
        self._event_bus = event_bus

        # Combat state
        self.max_strength = unit_type.max_strength
        self.strength = self.max_strength
        self.alive = True

        # Morale
        self.suppressed = False
        self.fallback = False

        # Spotting (runtime)
        self.spotted_enemies: set[str] = set()
        self.last_seen_turn: dict[str, int] = {}

        # Transport
        self.embarked = False
        self.carrier_id = None

        if self.unit_type.category.name == "VEHICLE":
            self.passengers = []

    # ----------------------------
    @property
    def hp(self) -> int:
        return self.strength

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
    def move_to(self, q: int, r: int):
        if self.embarked:
            raise RuntimeError(f"Embarked unit {self.unit_id} cannot move")
        self.position = (q, r)

    # ----------------------------
    def get_distance_to(self, other: "UnitInstance") -> int:
        if self.position is None or other.position is None:
            return 999
        return safe_hex_distance(self.position, other.position)

    # ----------------------------
    def get_attack_dice(self, target: "UnitInstance"):

        if not self.alive or target is None:
            return []

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
    # Spotting
    # ----------------------------
    def can_see(self, other: "UnitInstance") -> bool:
        return other.unit_id in self.spotted_enemies

    def remember_enemy(self, enemy_id: str, turn: int):
        self.spotted_enemies.add(enemy_id)
        self.last_seen_turn[enemy_id] = turn

    def forget_enemy(self, enemy_id: str):
        self.spotted_enemies.discard(enemy_id)

    # ----------------------------
    # Embark
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
            raise RuntimeError(f"{self.unit_id} not embarked")

        self.embarked = False
        self.carrier_id = None
        self.position = (q, r)

        if self.unit_id in getattr(vehicle, "passengers", []):
            vehicle.passengers.remove(self.unit_id)

        _trace("DISEMBARK", unit=self.unit_id, vehicle=vehicle.unit_id)

    # ----------------------------
    # Damage
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
            self._event_bus.emit({
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
            })

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

    def clear_suppression(self):
        if self.suppressed:
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

        if self.unit_type.category.name == "ARTILLERY":
            self.alive = False

    def clear_fallback(self):
        if self.fallback:
            self.fallback = False
            _trace("FALLBACK_CLEARED", unit=self.unit_id)

    # ==================================================
    # ✅ 🔥 CRÍTICO: optimización deepcopy
    # ==================================================
    def __getstate__(self):
        state = self.__dict__.copy()

        # ✅ NO copiar estado dinámico (spotting)
        state["spotted_enemies"] = set()
        state["last_seen_turn"] = {}

        return state
    
    # ==================================================
    # 🔥 COMBAT MODELING HELPERS
    # ==================================================

    def get_attack_power_vs(self, target: "UnitInstance") -> float:
        """
        Approximate offensive power based on attack dice.
        """

        dice = self.get_attack_dice(target)

        # pesos simples por dado (ajustables)
        weights = {
            "RED": 1.0,
            "YELLOW": 0.75,
            "GREEN": 0.5,
            "BLUE": 0.4,
        }

        power = 0.0
        for d in dice:
            power += weights.get(d.name, 0.5)

        # ajustar por HP (unidad dañada pega menos)
        hp_factor = self.hp / max(1, self.max_strength)

        return power * hp_factor

    # --------------------------------------------------
    def get_expected_damage(self, target: "UnitInstance") -> float:
        """
        Expected damage proxy.
        """

        return self.get_attack_power_vs(target)

    # --------------------------------------------------
    def get_combat_advantage(self, target: "UnitInstance") -> float:

        if target is None or not target.alive:
            return 0.0

        # --- attack power ---
        my_attack = self.get_attack_power_vs(target)
        enemy_attack = target.get_attack_power_vs(self)

        # 💥 caso crítico: no puede hacer daño
        if my_attack == 0:
            return -2.0

        # --- distancia ---
        distance = self.get_distance_to(target)

        range_factor = 1.0
        if distance > 6:
            range_factor = 0.6
        elif distance > 3:
            range_factor = 0.8

        # --- HP ---
        my_hp_ratio = self.hp / max(1, self.max_strength)
        enemy_hp_ratio = target.hp / max(1, target.max_strength)

        hp_advantage = (my_hp_ratio - enemy_hp_ratio) * 1.5

        # --- final ---
        advantage = (
            my_attack * 2.0 * range_factor
            - enemy_attack * 1.5
            + hp_advantage
        )

        return advantage

    # --------------------------------------------------
    def is_favorable_vs(self, target: "UnitInstance") -> bool:
        return self.get_combat_advantage(target) > 0

    # --------------------------------------------------
    def is_unfavorable_vs(self, target: "UnitInstance") -> bool:
        return self.get_combat_advantage(target) < -1.0
