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
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# -------------------------------------------------
# ✅ DISTANCIA OPTIMIZADA
# -------------------------------------------------
def _min_dist_fast(units_a, units_b):
    best = 999

    for a in units_a:
        for b in units_b:
            d = hex_distance(a.position, b.position)
            if d < best:
                best = d
                if best <= 1:
                    return best  # early stop
    return best


# -------------------------------------------------
# ✅ TRAINING ENV
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

        # ✅ FIX CRÍTICO → YAML en vez de JSON
        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = yaml.safe_load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        self.scenario_override = scenario_override
        self.current_step = 0

        self.reward_fn = ProgressiveReward(rl_side)

        # stats
        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

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

        # cache VP
        self._vp_hexes.clear()
        if state.vp_tracker and getattr(state.vp_tracker, "conditions", None):
            for vp in state.vp_tracker.conditions.points:
                self._vp_hexes.add(vp.hex_coords)

        return encode_state(
            state,
            rl_side=self.rl_side,
            max_turns=self.sim.scenario.max_turns,
        )

    # -------------------------------------------------
    def step(self, action):

        state = self.sim.game_state
        if state is None:
            raise RuntimeError("GameState is None")

        active = state.active_unit
        actor_side = active.side if active else None

        # -------------------------------------------------
        # COHERENCE
        # -------------------------------------------------
        if active is None:
            action = WaitAction("SYSTEM")
        elif action is not None and action.unit_id != active.unit_id:
            action = WaitAction(active.unit_id)

        is_wait = isinstance(action, WaitAction)

        # -------------------------------------------------
        # SNAPSHOT BEFORE
        # -------------------------------------------------
        hp_before = {u.unit_id: getattr(u, "hp", 0) for u in state.units}
        alive_before = {u.unit_id: bool(u.alive) for u in state.units}

        own_units = [u for u in state.units if u.alive and u.side == self.rl_side]
        enemy_units = [u for u in state.units if u.alive and u.side != self.rl_side]

        pre_dist = None
        if own_units and enemy_units:
            pre_dist = _min_dist_fast(own_units, enemy_units)

        # -------------------------------------------------
        # STEP
        # -------------------------------------------------
        next_state, _, sim_done, _ = self.sim.step(action)

        action_name = action.__class__.__name__ if action else ""
        is_attack = ("Ranged" in action_name) or ("Close" in action_name)

        if actor_side == self.rl_side and is_attack:
            self.rl_attacks += 1

        # -------------------------------------------------
        # SNAPSHOT AFTER
        # -------------------------------------------------
        hp_after = {u.unit_id: getattr(u, "hp", 0) for u in next_state.units}
        alive_after = {u.unit_id: bool(u.alive) for u in next_state.units}

        # -------------------------------------------------
        # RL INFO
        # -------------------------------------------------
        rl_info = {
            "damage": 0,
            "defender_killed": False,
            "is_wait": is_wait,
        }

        for unit_id, before_hp in hp_before.items():
            after_hp = hp_after.get(unit_id, before_hp)
            damage = max(0, before_hp - after_hp)

            if actor_side == self.rl_side and is_attack:
                self.rl_damage += damage
                rl_info["damage"] += damage

            if alive_before.get(unit_id, False) and not alive_after.get(unit_id, True):
                if actor_side == self.rl_side and is_attack:
                    self.rl_kills += 1
                    rl_info["defender_killed"] = True

        _trace(
            "COMBAT",
            action=action_name,
            dmg=rl_info["damage"],
            kills=self.rl_kills,
        )

        # -------------------------------------------------
        # DIST AFTER
        # -------------------------------------------------
        post_dist = None
        next_own = [u for u in next_state.units if u.alive and u.side == self.rl_side]
        next_enemy = [u for u in next_state.units if u.alive and u.side != self.rl_side]

        if next_own and next_enemy:
            post_dist = _min_dist_fast(next_own, next_enemy)

        # -------------------------------------------------
        # ✅ REWARD SOLO RL
        # -------------------------------------------------
        if actor_side == self.rl_side:
            reward = self.reward_fn.compute(
                state=state,
                next_state=next_state,
                action=action,
                active=active,
                info=rl_info,
                pre_dist=pre_dist,
                post_dist=post_dist,
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

        # -------------------------------------------------
        # INFO
        # -------------------------------------------------
        info = {
            "rl_damage": self.rl_damage,
            "rl_kills": self.rl_kills,
            "rl_attacks": self.rl_attacks,
            "is_wait": is_wait,
            "turn": next_state.turn,
            "done": done,
        }

        return (
            encode_state(
                next_state,
                rl_side=self.rl_side,
                max_turns=self.sim.scenario.max_turns,
            ),
            reward,
            done,
            info,
        )