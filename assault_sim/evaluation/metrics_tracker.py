from collections import defaultdict


# -------------------------------------------------
# PER-UNIT STATS
# -------------------------------------------------
class UnitStats:
    def __init__(self):
        self.attacks = 0

        self.ranged = 0
        self.melee = 0

        # ✅ NUEVO
        self.direct = 0
        self.indirect = 0

        self.damage_done = 0
        self.damage_taken = 0

        # ✅ NUEVO
        self.direct_damage = 0
        self.indirect_damage = 0

        self.kills = 0

        # ✅ NUEVO
        self.direct_kills = 0
        self.indirect_kills = 0

        self.alive = True


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

    def _side(self, unit_side):
        return "RL" if unit_side == self.rl_side else "ENEMY"

    # -------------------------------------------------
    # ✅ ACTION TRACKING (DIRECT vs INDIRECT)
    # -------------------------------------------------
    def track_action(self, state, action):
        active = state.active_unit

        if active is None or action is None:
            return

        unit_id = active.unit_id
        side = self._side(active.side)

        name = action.__class__.__name__

        is_ranged = "Ranged" in name
        is_melee = "Assault" in name or "Close" in name
        is_attack = is_ranged or is_melee

        is_indirect = "Indirect" in name
        is_direct = is_ranged and not is_indirect

        if is_attack:
            self.units[unit_id].attacks += 1
            self.side[side]["attacks"] += 1

            if is_ranged:
                self.units[unit_id].ranged += 1

            if is_melee:
                self.units[unit_id].melee += 1

            # ✅ NUEVO
            if is_direct:
                self.units[unit_id].direct += 1
                self.side[side]["direct"] += 1

            if is_indirect:
                self.units[unit_id].indirect += 1
                self.side[side]["indirect"] += 1

    # -------------------------------------------------
    # ✅ DAMAGE (CON DESGLOSE)
    # -------------------------------------------------
    def track_damage(self, info, state, prev_state):
        before = {u.unit_id: u.hp for u in prev_state.units}
        after = {u.unit_id: u.hp for u in state.units}

        attacker = prev_state.active_unit

        action = prev_state.last_action if hasattr(prev_state, "last_action") else None
        name = action.__class__.__name__ if action else ""

        is_indirect = "Indirect" in name
        is_direct = "Ranged" in name and not is_indirect

        for unit_id, hp_before in before.items():
            hp_after = after.get(unit_id, hp_before)

            dmg = max(0, hp_before - hp_after)

            if dmg <= 0:
                continue

            target_unit = next((u for u in state.units if u.unit_id == unit_id), None)
            if target_unit is None:
                continue

            target_side = self._side(target_unit.side)
            attacker_side = "RL" if target_side == "ENEMY" else "ENEMY"

            # global
            self.side[attacker_side]["damage"] += dmg

            # target recibe
            self.units[unit_id].damage_taken += dmg

            # atacante hace
            if attacker is not None:
                self.units[attacker.unit_id].damage_done += dmg

                if is_direct:
                    self.units[attacker.unit_id].direct_damage += dmg

                if is_indirect:
                    self.units[attacker.unit_id].indirect_damage += dmg

    # -------------------------------------------------
    # ✅ KILLS (DESGLOSE)
    # -------------------------------------------------
    def track_kills(self, state, prev_state):
        prev_alive = {u.unit_id: u.alive for u in prev_state.units}
        attacker = prev_state.active_unit

        action = prev_state.last_action if hasattr(prev_state, "last_action") else None
        name = action.__class__.__name__ if action else ""

        is_indirect = "Indirect" in name
        is_direct = "Ranged" in name and not is_indirect

        for u in state.units:

            if prev_alive.get(u.unit_id, True) and not u.alive:

                if not self.units[u.unit_id].alive:
                    continue

                side = self._side(u.side)
                killer_side = "RL" if side == "ENEMY" else "ENEMY"

                self.side[killer_side]["kills"] += 1

                if attacker is not None:
                    self.units[attacker.unit_id].kills += 1

                    if is_direct:
                        self.units[attacker.unit_id].direct_kills += 1

                    if is_indirect:
                        self.units[attacker.unit_id].indirect_kills += 1

                self.units[u.unit_id].alive = False

    # -------------------------------------------------
    def track_state(self, state):
        vp = state.vp_tracker.total_points if state.vp_tracker else 0
        self.vp_progression.append(vp)

    def step(self):
        self.steps += 1

    # -------------------------------------------------
    # ✅ OUTPUT
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
            "units": self.units,
            "vp_progression": self.vp_progression,
        }