import json
import random
import yaml
import os
from pathlib import Path
import numpy as np
import torch

from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import safe_hex_distance

from assault_sim.rl.state_encoder import encode_state
from assault_sim.rewards.progressive_reward import ProgressiveReward


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return


# -------------------------------------------------
def _min_dist_fast(units_a, units_b):
    best = 999

    for a in units_a:
        for b in units_b:
            d = safe_hex_distance(a.position, b.position)
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
        reward_fn=None,   # ✅ NUEVO
        seed: int | None = None,
    ):
        self.sim = sim_env
        self.rl_side = rl_side
        self.base_seed = seed
        self.reset_count = 0

        with open(env_config_path, "r", encoding="utf-8") as f:
            if str(env_config_path).lower().endswith(".json"):
                self.env_config = json.load(f)
            else:
                self.env_config = yaml.safe_load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", self.env_config.get("max_steps", None))

        self.scenario_override = scenario_override
        self.current_step = 0

        self.reward_fn = reward_fn or ProgressiveReward(rl_side)

        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.enemy_attacks = 0
        self.enemy_damage = 0
        self.enemy_kills = 0

        self._vp_hexes = set()

    def _objectives_captured_for_side(self, state, side: str) -> int:
        if state is None or not side:
            return 0
        points = getattr(getattr(state, "victory", None), "points", []) or []
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        ownership = side_to_ownership.get(str(side).upper())
        if ownership is None:
            return 0
        captured = 0
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == ownership:
                captured += 1
        return captured

    # -------------------------------------------------
    @property
    def state(self):
        return self.sim.game_state

    # -------------------------------------------------
    def reset(self):
        if self.base_seed is not None:
            current_seed = int(self.base_seed) + self.reset_count
            random.seed(current_seed)
            np.random.seed(current_seed)
            torch.manual_seed(current_seed)
            self.reset_count += 1

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
            scenario=self.sim.scenario,
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
        objective_cfg = getattr(self.sim.scenario, "victory_outcomes", None) or {}
        tracked_side = str(objective_cfg.get("tracked_side", "")).strip().upper()
        objective_rule_active = (
            str(objective_cfg.get("metric", "")).strip() == "objectives_captured"
            and str(objective_cfg.get("timing", "")).strip() == "end_of_last_turn"
            and bool(objective_cfg.get("table"))
            and bool(tracked_side)
        )
        captured_before = (
            self._objectives_captured_for_side(state, tracked_side)
            if objective_rule_active
            else 0
        )

        # -------------------------------------------------
        # STEP
        # -------------------------------------------------
        next_state, _, sim_done, _ = self.sim.step(action)

        action_name = action.__class__.__name__
        name = action_name.lower()

        # -------------------------------------------------
        # ACTION TYPE
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

        is_attack = action_type in ["direct", "indirect", "assault"]

        if DEBUG_TRACE:
            print(f"⚙️ ACTION: {action_name} -> {action_type}")

        # -------------------------------------------------
        # ✅ INFO (FIX AÑADIDO)
        # -------------------------------------------------
        info = {
            "unit_id": action.unit_id if hasattr(action, "unit_id") else None,
            "action_id": getattr(action, "action_id", None),  # ✅ 💣 NUEVO
            "actor_side": actor_side,

            "rl_damage": 0,
            "rl_attacks": 0,
            "rl_kills": 0,
            "enemy_damage": 0,
            "enemy_attacks": 0,
            "enemy_kills": 0,
            "is_wait": is_wait,
            "action_type": action_type,
            "action_class": action.__class__.__name__,
            "turn": next_state.turn,
        }

        # -------------------------------------------------
        # ATTACKS
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
        captured_after = (
            self._objectives_captured_for_side(next_state, tracked_side)
            if objective_rule_active
            else 0
        )

        # -------------------------------------------------
        # DAMAGE & KILLS
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
        # ✅ DISTANCIA AL ENEMIGO (antes/después)
        # Reactiva el shaping de aproximación/presión en la recompensa.
        # Se mide la distancia de la unidad que actúa a su enemigo más
        # cercano, antes y después de aplicar la acción.
        # -------------------------------------------------
        pre_dist = None
        post_dist = None

        if actor is not None and actor_side == self.rl_side:
            enemies_before = [
                u for u in state.units
                if u.alive and u.side != self.rl_side and u.position is not None
            ]
            if actor.position is not None and enemies_before:
                pre_dist = min(
                    safe_hex_distance(actor.position, e.position)
                    for e in enemies_before
                )

            actor_after = next(
                (u for u in next_state.units if u.unit_id == actor.unit_id),
                None,
            )
            enemies_after = [
                u for u in next_state.units
                if u.alive and u.side != self.rl_side and u.position is not None
            ]
            if (
                actor_after is not None
                and actor_after.position is not None
                and enemies_after
            ):
                post_dist = min(
                    safe_hex_distance(actor_after.position, e.position)
                    for e in enemies_after
                )

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

        info["done"] = done
        info["objective_rule_active"] = objective_rule_active
        info["objective_tracked_side"] = tracked_side if objective_rule_active else None
        info["objective_captured_before"] = captured_before
        info["objective_captured_after"] = captured_after
        info["objective_captured_delta"] = captured_after - captured_before

        return (
            encode_state(
                next_state,
                unit=None,
                rl_side=self.rl_side,
                max_turns=self.sim.scenario.max_turns,
                scenario=self.sim.scenario,
            ),
            reward,
            done,
            info,
        )