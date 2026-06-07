from collections import defaultdict


class MetricsTracker:

    def __init__(self, rl_side: str, scenario=None):
        self.rl_side = rl_side
        self.scenario = scenario
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

        # SIDE DETECTION (no hardcoded prefixes)
        side = None
        if state is not None and hasattr(state, "units"):
            actor = next((u for u in state.units if u.unit_id == unit_id), None)
            if actor is not None:
                side = "RL" if getattr(actor, "side", None) == self.rl_side else "ENEMY"
        if side is None:
            actor_side = info.get("actor_side")
            if actor_side is not None:
                side = "RL" if actor_side == self.rl_side else "ENEMY"
        if side is None:
            side = "RL" if info.get("rl_attacks", 0) > 0 else "ENEMY"

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
        # Ensure every unit in the state has an entry in unit_stats with metadata
        if state is None or not hasattr(state, "units"):
            return

        for u in state.units:
            uid = getattr(u, "unit_id", None)
            if not uid:
                continue

            side = "RL" if getattr(u, "side", None) == self.rl_side else "ENEMY"

            entry = self.unit_stats[side][uid]

            # populate metadata if available
            if entry.get("unit_key") is None:
                ut = getattr(u, "unit_type", None)
                if ut:
                    entry["unit_key"] = getattr(ut, "code", None)
                    entry["category"] = getattr(ut.category, "value", None) if getattr(ut, "category", None) else None
                    entry["classification"] = getattr(ut, "classification", None)

            # ensure counts exist (default dict handles zeros)
            _ = entry["attacks"]
            _ = entry["damage"]
            _ = entry["kills"]

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

        vp_by_side = {}
        vp_total_in_play = 0
        rl_vp = 0
        if game_state is not None:
            victory = getattr(game_state, "victory", None)
            hex_states = getattr(game_state, "hex_states", {}) or {}
            side_to_ownership = getattr(game_state, "side_to_ownership", {}) or {}
            ownership_to_side = {
                ownership: side for side, ownership in side_to_ownership.items()
            }
            if victory is not None:
                for vp in getattr(victory, "points", []):
                    value = int(getattr(vp, "per_turn", 0))
                    vp_total_in_play += value
                    hs = hex_states.get(vp.hex_coords)
                    owner = getattr(hs, "ownership", None)
                    side = ownership_to_side.get(owner)
                    if side:
                        vp_by_side[side] = vp_by_side.get(side, 0) + value
            rl_vp = int(vp_by_side.get(self.rl_side, 0))

        victory_level = None
        if self.scenario is not None:
            outcomes = getattr(self.scenario, "victory_outcomes", None) or {}
            if (
                str(outcomes.get("metric", "")).strip() == "objectives_captured"
                and str(outcomes.get("timing", "")).strip() == "end_of_last_turn"
                and outcomes.get("table")
            ):
                tracked_side = str(outcomes.get("tracked_side", "")).strip().upper()
                captured = 0
                total_obj = 0
                if tracked_side and game_state is not None:
                    points = getattr(getattr(game_state, "victory", None), "points", []) or []
                    total_obj = len(points)
                    side_to_ownership = getattr(game_state, "side_to_ownership", {}) or {}
                    tracked_owner = side_to_ownership.get(tracked_side)
                    for vp in points:
                        hs = game_state.hex_states.get(vp.hex_coords)
                        if hs is not None and hs.ownership == tracked_owner:
                            captured += 1
                matched = None
                for row in outcomes.get("table", []):
                    cap = row.get("captured", {}) if isinstance(row, dict) else {}
                    try:
                        min_cap = int(cap.get("min", -10**9))
                        max_cap = int(cap.get("max", 10**9))
                    except Exception:
                        continue
                    if min_cap <= captured <= max_cap:
                        matched = row
                        break
                victory_level = {
                    "tracked_side": tracked_side,
                    "captured": captured,
                    "objectives_total": total_obj,
                    "result": (matched or {}).get("result"),
                }
        tracked_result = (victory_level or {}).get("result")
        winner = getattr(game_state, "winner", None)
        if winner is None:
            rl_result = "draw"
        elif str(winner).upper() == str(self.rl_side).upper():
            rl_result = "win"
        else:
            rl_result = "loss"

        return {
            "winner": winner,
            "end_reason": getattr(game_state, "end_reason", None),
            "rl_result": rl_result,
            "tracked_result": tracked_result,
            "vp": rl_vp,
            "vp_by_side": vp_by_side,
            "vp_total_in_play": vp_total_in_play,
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
            "victory_level": victory_level,

            "units": units_output,
        }