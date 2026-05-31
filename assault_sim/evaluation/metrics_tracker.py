from collections import defaultdict


class MetricsTracker:

    def __init__(self, rl_side: str):
        self.rl_side = rl_side
        self.debug = True
        self.reset()

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):

        # -------------------------------
        # SIDE TOTALS
        # -------------------------------
        self.side_totals = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        # -------------------------------
        # L1 USAGE
        # -------------------------------
        self.l1 = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        # -------------------------------
        # L1 COMBAT STATS
        # -------------------------------
        self.l1_stats = {
            "RL": defaultdict(lambda: {"damage": 0, "kills": 0, "attacks": 0}),
            "ENEMY": defaultdict(lambda: {"damage": 0, "kills": 0, "attacks": 0}),
        }

        # -------------------------------
        # UNIT STATS (EXTENDIDO)
        # -------------------------------
        self.unit_stats = {
            "RL": defaultdict(lambda: {
                "damage": 0,
                "attacks": 0,
                "kills": 0,
                "unit_key": None,
                "category": None,
                "classification": None,
            }),
            "ENEMY": defaultdict(lambda: {
                "damage": 0,
                "attacks": 0,
                "kills": 0,
                "unit_key": None,
                "category": None,
                "classification": None,
            }),
        }

        self.steps = 0

        # -------------------------------
        # COMBAT INTELLIGENCE
        # -------------------------------
        self.trade_sum = 0.0
        self.trade_count = 0

        self.bad_attacks = 0
        self.total_attacks = 0

        self.damage_taken_total = 0

    # -------------------------------------------------
    # CORE TRACKING
    # -------------------------------------------------
    def track_damage(self, info, state, prev_state):

        if not info:
            return

        # -------------------------------------------------
        # UNIT ID robusto
        # -------------------------------------------------
        unit_id = info.get("unit_id")

        if not unit_id:
            unit_id = info.get("actor_id") or info.get("source_id") or "UNKNOWN"

        # SIDE DETECTION
        is_rl = unit_id.startswith("US")
        side = "RL" if is_rl else "ENEMY"

        # -------------------------------
        # RAW VALUES
        # -------------------------------
        rl_attacks = info.get("rl_attacks", 0)
        rl_damage = info.get("rl_damage", 0)
        rl_kills = info.get("rl_kills", 0)

        enemy_attacks = info.get("enemy_attacks", 0)
        enemy_damage = info.get("enemy_damage", 0)
        enemy_kills = info.get("enemy_kills", 0)

        # -------------------------------------------------
        # SIDE TOTALS
        # -------------------------------------------------
        if rl_attacks > 0:
            self.side_totals["RL"]["attacks"] += rl_attacks
        if rl_damage > 0:
            self.side_totals["RL"]["damage"] += rl_damage
        if rl_kills > 0:
            self.side_totals["RL"]["kills"] += rl_kills

        if enemy_attacks > 0:
            self.side_totals["ENEMY"]["attacks"] += enemy_attacks
        if enemy_damage > 0:
            self.side_totals["ENEMY"]["damage"] += enemy_damage
        if enemy_kills > 0:
            self.side_totals["ENEMY"]["kills"] += enemy_kills

        # -------------------------------------------------
        # L1 USAGE
        # -------------------------------------------------
        action_class = info.get("action_class") or "unknown"
        self.l1[side][action_class] += 1

        # -------------------------------------------------
        # L1 COMBAT STATS
        # -------------------------------------------------
        if rl_attacks > 0:
            entry = self.l1_stats["RL"][action_class]
            entry["attacks"] += rl_attacks
            entry["damage"] += rl_damage
            entry["kills"] += rl_kills

        if enemy_attacks > 0:
            entry = self.l1_stats["ENEMY"][action_class]
            entry["attacks"] += enemy_attacks
            entry["damage"] += enemy_damage
            entry["kills"] += enemy_kills

        # -------------------------------------------------
        # UNIT OBJECT (clave)
        # -------------------------------------------------
        unit_obj = None
        if state is not None and hasattr(state, "units"):
            unit_obj = next((u for u in state.units if u.unit_id == unit_id), None)

        # -------------------------------------------------
        # UNIT STATS + METADATA (FIX REAL)
        # -------------------------------------------------
        if rl_attacks > 0:
            entry = self.unit_stats["RL"][unit_id]
            entry["attacks"] += rl_attacks
            entry["damage"] += rl_damage
            entry["kills"] += rl_kills

            if unit_obj and entry["unit_key"] is None:
                ut = getattr(unit_obj, "unit_type", None)

                if ut:
                    entry["unit_key"] = getattr(ut, "code", None)
                    entry["category"] = getattr(ut.category, "value", None) if ut.category else None
                    entry["classification"] = getattr(ut, "classification", None)

        if enemy_attacks > 0:
            entry = self.unit_stats["ENEMY"][unit_id]
            entry["attacks"] += enemy_attacks
            entry["damage"] += enemy_damage
            entry["kills"] += enemy_kills

            if unit_obj and entry["unit_key"] is None:
                ut = getattr(unit_obj, "unit_type", None)

                if ut:
                    entry["unit_key"] = getattr(ut, "code", None)
                    entry["category"] = getattr(ut.category, "value", None) if ut.category else None
                    entry["classification"] = getattr(ut, "classification", None)

        # -------------------------------------------------
        # COMBAT INTELLIGENCE
        # -------------------------------------------------
        self.damage_taken_total += enemy_damage

        if rl_attacks > 0:
            trade = rl_damage - enemy_damage

            self.trade_sum += trade
            self.trade_count += 1

            if enemy_damage > rl_damage:
                self.bad_attacks += 1

            self.total_attacks += 1

    # -------------------------------------------------
    def track_state(self, state):
        pass

    # -------------------------------------------------
    def step(self):
        self.steps += 1

    # -------------------------------------------------
    # RESULT BUILD
    # -------------------------------------------------
    def build_result(self, game_state):

        rl_damage = self.side_totals["RL"]["damage"]

        damage_ratio = rl_damage / max(1, self.damage_taken_total)
        trade_mean = self.trade_sum / max(1, self.trade_count)
        bad_attack_rate = self.bad_attacks / max(1, self.total_attacks)

        def compute_l1_efficiency(data):
            result = {}
            for k, v in data.items():
                attacks = v["attacks"]
                result[k] = {
                    "damage_per_attack": v["damage"] / max(1, attacks),
                    "kills_per_attack": v["kills"] / max(1, attacks),
                }
            return result

        l1_eff = {
            "RL": compute_l1_efficiency(self.l1_stats["RL"]),
            "ENEMY": compute_l1_efficiency(self.l1_stats["ENEMY"]),
        }

        units_output = {
            "RL": {k: dict(v) for k, v in self.unit_stats["RL"].items()},
            "ENEMY": {k: dict(v) for k, v in self.unit_stats["ENEMY"].items()},
        }

        return {
            "winner": getattr(game_state, "winner", None),
            "vp": getattr(game_state, "vp", 0),
            "steps": self.steps,

            "side": {
                "RL": dict(self.side_totals["RL"]),
                "ENEMY": dict(self.side_totals["ENEMY"]),
            },

            "l1": {
                "RL": dict(self.l1["RL"]),
                "ENEMY": dict(self.l1["ENEMY"]),
            },

            "l1_efficiency": l1_eff,

            "combat": {
                "trade_mean": trade_mean,
                "bad_attack_rate": bad_attack_rate,
                "damage_ratio": damage_ratio,
                "total_attacks": self.total_attacks,
            },

            "units": units_output,
        }