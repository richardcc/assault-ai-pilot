import yaml
import os
from pathlib import Path

from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import hex_distance

from assault_sim.rl.state_encoder import encode_state
from assault_sim.rewards.aggressive_reward import ProgressiveReward


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return


# -------------------------------------------------
def _min_dist_fast(units_a, units_b):
    best = 999

    for a in units_a:
        for b in units_b:
            d = hex_distance(a.position, b.position)
            if d < best:
                best = d
                if best <= 1:
                    return best
    return best


# -------------------------------------------------
class TrainingEnv:

    def __init__(
        self,
        sim_env,
        env_config_path: Path,
        rl_side: str,
        scenario_override=None,
    ):
        self.sim = sim_env
        self.rl_side = rl_side

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = yaml.safe_load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        self.scenario_override = scenario_override
        self.current_step = 0

        self.reward_fn = ProgressiveReward(rl_side)

        # acumulados globales
        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.enemy_attacks = 0
        self.enemy_damage = 0
        self.enemy_kills = 0

        self._vp_hexes = set()

    # -------------------------------------------------
    @property
    def state(self):
        return self.sim.game_state

    # -------------------------------------------------
    def reset(self):

        state = self.sim.reset()

        self.current_step = 0
        self.reward_fn.reset(state)

        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.enemy_attacks = 0
        self.enemy_damage = 0
        self.enemy_kills = 0

        self._vp_hexes.clear()

        return encode_state(
            state,
            unit=None,
            rl_side=self.rl_side,
            max_turns=self.sim.scenario.max_turns,
        )

    # -------------------------------------------------
    def step(self, action):

        state = self.sim.game_state

        actor = None
        actor_side = None

        if action is not None and hasattr(action, "unit_id"):
            actor = next(
                (u for u in state.units if u.unit_id == action.unit_id),
                None,
            )
            actor_side = actor.side if actor else None

        if action is None:
            action = WaitAction("SYSTEM")

        is_wait = isinstance(action, WaitAction)

        # -------------------------------------------------
        # SNAPSHOT BEFORE
        # -------------------------------------------------
        hp_before = {u.unit_id: u.hp for u in state.units}
        alive_before = {u.unit_id: u.alive for u in state.units}

        # -------------------------------------------------
        # STEP
        # -------------------------------------------------
        next_state, _, sim_done, _ = self.sim.step(action)

        action_name = action.__class__.__name__
        name = action_name.lower()

        # -------------------------------------------------
        # ✅ ACTION TYPE (ROBUSTO)
        # 🔥 ORDEN CRÍTICO: específico → general
        # -------------------------------------------------
        if is_wait:
            action_type = "wait"

        elif "close" in name:
            action_type = "direct"

        elif "assault" in name:
            action_type = "assault"

        elif "ranged" in name:
            action_type = "indirect"

        elif "move" in name:
            action_type = "move"

        else:
            action_type = "unknown"

        # ✅ usar action_type como fuente única de verdad
        is_attack = action_type in ["direct", "indirect", "assault"]

        # DEBUG útil
        if DEBUG_TRACE:
            print(f"⚙️ ACTION: {action_name} -> {action_type}")

        # -------------------------------------------------
        # ✅ INFO (DELTA POR STEP)
        # -------------------------------------------------
        info = {
            "unit_id": action.unit_id if hasattr(action, "unit_id") else None,
            "rl_damage": 0,
            "rl_attacks": 0,
            "rl_kills": 0,
            "enemy_damage": 0,
            "enemy_attacks": 0,
            "enemy_kills": 0,
            "is_wait": is_wait,
            "action_type": action_type,                      # categoría simple
            "action_class": action.__class__.__name__,       # ✅ REAL (LO IMPORTANTE)
            "turn": next_state.turn,
        }

        # -------------------------------------------------
        # ATAQUES
        # -------------------------------------------------
        if is_attack:
            if actor_side == self.rl_side:
                self.rl_attacks += 1
                info["rl_attacks"] += 1
            else:
                self.enemy_attacks += 1
                info["enemy_attacks"] += 1

        # -------------------------------------------------
        # SNAPSHOT AFTER
        # -------------------------------------------------
        hp_after = {u.unit_id: u.hp for u in next_state.units}
        alive_after = {u.unit_id: u.alive for u in next_state.units}

        # -------------------------------------------------
        # DAÑO Y KILLS
        # -------------------------------------------------
        for uid, before_hp in hp_before.items():
            after_hp = hp_after.get(uid, before_hp)
            damage = max(0, before_hp - after_hp)

            if damage == 0:
                continue

            if is_attack:
                if actor_side == self.rl_side:
                    self.rl_damage += damage
                    info["rl_damage"] += damage
                else:
                    self.enemy_damage += damage
                    info["enemy_damage"] += damage

            if alive_before[uid] and not alive_after.get(uid, True):
                if is_attack:
                    if actor_side == self.rl_side:
                        self.rl_kills += 1
                        info["rl_kills"] += 1
                    else:
                        self.enemy_kills += 1
                        info["enemy_kills"] += 1

        # -------------------------------------------------
        # REWARD
        # -------------------------------------------------
        if actor_side == self.rl_side:
            reward = self.reward_fn.compute(
                state=state,
                next_state=next_state,
                action=action,
                active=actor,
                info=info,
                pre_dist=None,
                post_dist=None,
            )
        else:
            reward = 0.0

        # -------------------------------------------------
        # DONE
        # -------------------------------------------------
        self.current_step += 1
        done = sim_done

        if self.max_steps and self.current_step >= self.max_steps:
            done = True

        info["done"] = done

        return (
            encode_state(
                next_state,
                unit=None,
                rl_side=self.rl_side,
                max_turns=self.sim.scenario.max_turns,
            ),
            reward,
            done,
            info,
        )