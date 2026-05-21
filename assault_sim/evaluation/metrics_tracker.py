from collections import defaultdict


class MetricsTracker:

    def __init__(self, rl_side: str):
        self.rl_side = rl_side
        self.debug = True

        # -------------------------------
        # SIDE TOTALS
        # -------------------------------
        self.side_totals = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        # -------------------------------
        # ✅ L1 = CLASS NAME DIRECTO 🔥
        # -------------------------------
        self.l1 = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        self.steps = 0

    # -------------------------------------------------
    # CORE
    # -------------------------------------------------

    def track_damage(self, info, state, prev_state):

        if not info:
            return

        unit_id = info.get("unit_id", "")
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
        # ✅ SIDE TOTALS
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
        # ✅ 🔥 L1 = CLASS NAME REAL (LO QUE QUIERES)
        # -------------------------------------------------
        action_class = info.get("action_class", "unknown")

        self.l1[side][action_class] += 1

    # -------------------------------------------------
    def track_state(self, state):
        pass

    # -------------------------------------------------
    def step(self):
        self.steps += 1

    # -------------------------------------------------
    def build_result(self, game_state):

        print("\n==============================")
        print("📊 FINAL TRACKER STATE")
        print("L1 RL:", dict(self.l1["RL"]))
        print("L1 ENEMY:", dict(self.l1["ENEMY"]))
        print("==============================\n")

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
            "units": {},
        }