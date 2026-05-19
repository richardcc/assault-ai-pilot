from collections import defaultdict


# -------------------------------------------------
# PER-UNIT STATS
# -------------------------------------------------
class UnitStats:
    def __init__(self):
        self.attacks = 0
        self.damage_done = 0
        self.damage_taken = 0
        self.kills = 0
        self.alive = True
        self.alive_count = 0
        self._last_hp = None


# -------------------------------------------------
# MAIN TRACKER
# -------------------------------------------------
class MetricsTracker:

    def __init__(self, rl_side: str):
        self.rl_side = rl_side
        self.reset()

    def reset(self):
        self.units = defaultdict(UnitStats)

        self.side = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        self.vp_progression = []
        self.steps = 0

    # -------------------------------------------------
    def _side(self, unit_id: str):
        return "RL" if unit_id.startswith(self.rl_side) else "ENEMY"

    # -------------------------------------------------
    # ✅ EVENT-BASED TRACKING (REPLAY / DEBUG)
    # -------------------------------------------------
    def on_event(self, event):

        if not event or event.get("type") != "ACTION_EFFECT":
            return

        payload = event.get("payload", {})

        attacker = payload.get("attacker")
        defender = payload.get("defender")

        if not attacker or not defender:
            return

        side = self._side(attacker)

        # ✅ contar ataque
        self.side[side]["attacks"] += 1
        self.units[attacker].attacks += 1

        # ✅ estimar daño desde dados
        attack_dice = payload.get("attack_dice", [])
        defense_dice = payload.get("defense_dice", [])

        hits = sum(1 for d in attack_dice if "HIT" in d or "CRIT" in d)
        blocks = sum(1 for d in defense_dice if "BLOCK" in d)

        damage = max(0, hits - blocks)

        self.side[side]["damage"] += damage
        self.units[attacker].damage_done += damage
        self.units[defender].damage_taken += damage

        # ✅ kill aproximado (puedes mejorar si tienes info de HP)
        if damage > 0:
            self.units[attacker].kills += 1
            self.side[side]["kills"] += 1

    # -------------------------------------------------
    # ✅ FALLBACK: INFO-BASED TRACKING (EVALUATION)
    # -------------------------------------------------
    def track_damage(self, info, state, prev_state):

        if not info:
            return

        unit_id = info.get("unit_id")
        if not unit_id:
            return

        side = self._side(unit_id)

        if side == "RL":
            damage = info.get("rl_damage", 0)
            attacks = info.get("rl_attacks", 0)
            kills = info.get("rl_kills", 0)
        else:
            damage = info.get("enemy_damage", 0)
            attacks = info.get("enemy_attacks", 0)
            kills = info.get("enemy_kills", 0)

        # ✅ GLOBAL
        self.side[side]["damage"] += damage
        self.side[side]["attacks"] += attacks
        self.side[side]["kills"] += kills

        # ✅ 🔥 POR UNIDAD (ESTO ERA LO QUE FALLABA)
        u = self.units[unit_id]
        u.damage_done += damage
        u.attacks += attacks
        u.kills += kills

        u.kills += kills

    # -------------------------------------------------
    def track_kills(self, state, prev_state, info=None):
        pass

    # -------------------------------------------------
    def track_state(self, state):

        # ✅ asegurar existencia de unidades
        for u in state.units:
            if u.unit_id not in self.units:
                self.units[u.unit_id] = UnitStats()

        # ✅ actualizar estado
        for u in state.units:
            stats = self.units[u.unit_id]

            stats.alive = u.alive

            if u.alive:
                stats.alive_count += 1

            prev_hp = stats._last_hp if stats._last_hp is not None else u.hp
            dmg_taken = max(0, prev_hp - u.hp)

            if dmg_taken > 0:
                stats.damage_taken += dmg_taken

            stats._last_hp = u.hp

    # -------------------------------------------------
    def step(self):
        self.steps += 1

    # -------------------------------------------------
    def build_result(self, final_state):

        def efficiency(side):
            a = self.side[side]["attacks"]
            d = self.side[side]["damage"]
            k = self.side[side]["kills"]

            return {
                "damage_per_attack": d / a if a else 0,
                "kills_per_attack": k / a if a else 0,
            }

        return {
            "winner": final_state.winner,
            "vp": final_state.vp_tracker.total_points if final_state.vp_tracker else 0,
            "steps": self.steps,
            "efficiency": {
                "RL": efficiency("RL"),
                "ENEMY": efficiency("ENEMY"),
            },
            "side": self.side,
            "units": dict(self.units),
            "vp_progression": self.vp_progression,
        }