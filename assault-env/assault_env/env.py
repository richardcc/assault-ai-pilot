import gymnasium as gym
from gymnasium import spaces
import random

from assault_env.scenario import simple_duel_level7_P1_from_json
from assault_env.agents.heuristic import HeuristicAgent

from assault.core.actions.movement_action import MovementAction
from assault.core.actions.movement_executor import MovementExecutor
from assault.core.actions.assault_executor import AssaultExecutor
from assault.core.spatial.zone_of_control import ZoneOfControlService


class AssaultEnv(gym.Env):
    """
    Gymnasium-compatible environment.

    Level 7:
    - Real geometry loaded from JSON (P1)
    - Full 2D movement (forward, backward, left, right)
    - Relative enemy vector (dx, dy)
    - Terrain-based cover
    - Heuristic opponent (break self-play)
    - Distance-based + directional reward shaping
    """

    metadata = {"render_modes": ["ascii"]}

    def __init__(self):
        super().__init__()

        # ------------------------------------------------------------
        # Action space
        # 0 = WAIT
        # 1 = MOVE_FORWARD
        # 2 = ASSAULT
        # 3 = RANGED_FIRE
        # 4 = MOVE_LEFT
        # 5 = MOVE_RIGHT
        # 6 = MOVE_BACKWARD
        # ------------------------------------------------------------
        self.action_space = spaces.Discrete(7)

        self.observation_space = spaces.Dict({
            "my_strength": spaces.Box(low=0, high=10, shape=(1,), dtype=int),
            "enemy_strength": spaces.Box(low=0, high=10, shape=(1,), dtype=int),
            "enemy_distance": spaces.Box(low=0, high=20, shape=(1,), dtype=int),
            "enemy_dx": spaces.Box(low=-10, high=10, shape=(1,), dtype=int),
            "enemy_dy": spaces.Box(low=-10, high=10, shape=(1,), dtype=int),
            "in_enemy_zoc": spaces.Box(low=0, high=1, shape=(1,), dtype=int),
            "can_assault": spaces.Box(low=0, high=1, shape=(1,), dtype=int),
        })

        self.state = None
        self.player_id = None
        self.enemy_id = None
        self.current_player_id = None
        self.opponent_player_id = None
        self.done = False

        # Heuristic opponent
        self.heuristic = HeuristicAgent()

    # ------------------------------------------------------------------
    # Gym API
    # ------------------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        # ✅ LEVEL 7 SCENARIO (JSON geometry)
        self.state, self.player_id, self.enemy_id = simple_duel_level7_P1_from_json()
        self.current_player_id = self.player_id
        self.opponent_player_id = self.enemy_id
        self.done = False

        return self._get_obs(self.current_player_id), {}

    def step(self, action: int):
        if self.done:
            raise RuntimeError("Episode already finished")

        # --------------------------------------------------------------
        # Heuristic controls enemy turns
        # --------------------------------------------------------------
        if self.current_player_id == self.enemy_id:
            obs = self._get_obs(self.current_player_id)
            action = self.heuristic.act(obs)

        reward = 0.0
        terminated = False
        truncated = False

        player = self.state.get_unit(self.current_player_id)
        enemy = self.state.units.get(self.opponent_player_id)

        # --- Distance BEFORE action ---
        if enemy:
            prev_dx = enemy.position[0] - player.position[0]
            prev_dy = enemy.position[1] - player.position[1]
            prev_distance = abs(prev_dx) + abs(prev_dy)
        else:
            prev_dx = prev_dy = prev_distance = 0

        executor = MovementExecutor(self.state)

        # --------------------------------------------------------------
        # Movement actions
        # --------------------------------------------------------------
        if action == 1:      # MOVE_FORWARD
            target = (player.position[0] + 1, player.position[1])
        elif action == 4:    # MOVE_LEFT
            target = (player.position[0], player.position[1] + 1)
        elif action == 5:    # MOVE_RIGHT
            target = (player.position[0], player.position[1] - 1)
        elif action == 6:    # MOVE_BACKWARD
            target = (player.position[0] - 1, player.position[1])
        else:
            target = None

        if target is not None:
            try:
                executor.execute(MovementAction(player, target))
            except ValueError:
                reward -= 0.1

        # --------------------------------------------------------------
        # ASSAULT
        # --------------------------------------------------------------
        elif action == 2 and enemy is not None:
            if prev_distance > 1:
                reward -= 1.0
            else:
                player_before = player.strength
                enemy_before = enemy.strength

                AssaultExecutor(
                    self.state,
                    self.current_player_id,
                    self.opponent_player_id,
                ).execute()

                enemy_after_obj = self.state.units.get(self.opponent_player_id)
                enemy_after = enemy_after_obj.strength if enemy_after_obj else 0
                player_after = player.strength

                reward += (enemy_before - enemy_after) - (player_before - player_after)

                if enemy_after_obj is None:
                    reward += 5.0

        # --------------------------------------------------------------
        # RANGED_FIRE
        # --------------------------------------------------------------
        elif action == 3 and enemy is not None:
            if prev_distance > 1:
                hit_chance = 0.5
                enemy_hex = self.state.hexes[enemy.position]
                if enemy_hex.terrain.defense_bonus > 0:
                    hit_chance *= 0.5

                if random.random() < hit_chance:
                    enemy.strength -= 1
                    reward += 1
                else:
                    reward -= 0.05
            else:
                reward -= 0.2

        # --------------------------------------------------------------
        # ✅ Distance-based + directional shaping
        # --------------------------------------------------------------
        if enemy and not terminated:
            new_dx = enemy.position[0] - player.position[0]
            new_dy = enemy.position[1] - player.position[1]
            new_distance = abs(new_dx) + abs(new_dy)

            # Global distance shaping
            if new_distance < prev_distance:
                reward += 0.05
            elif new_distance > prev_distance:
                reward -= 0.02

            # Directional shaping
            if abs(prev_dx) > abs(prev_dy):
                if abs(new_dx) < abs(prev_dx):
                    reward += 0.03
            else:
                if abs(new_dy) < abs(prev_dy):
                    reward += 0.03

        # --------------------------------------------------------------
        # Terminal conditions
        # --------------------------------------------------------------
        if self.state.units.get(self.opponent_player_id) is None:
            reward += 5.0
            terminated = True
            self.done = True

        if not player.is_alive():
            reward -= 5.0
            terminated = True
            self.done = True

        if not terminated:
            self.current_player_id, self.opponent_player_id = (
                self.opponent_player_id,
                self.current_player_id,
            )

        return self._get_obs(self.current_player_id), reward, terminated, truncated, {}

    # ------------------------------------------------------------------
    # Observation helper
    # ------------------------------------------------------------------

    def _get_obs(self, player_id):
        if player_id not in self.state.units:
            return {
                "my_strength": [0],
                "enemy_strength": [0],
                "enemy_distance": [0],
                "enemy_dx": [0],
                "enemy_dy": [0],
                "in_enemy_zoc": [0],
                "can_assault": [0],
            }

        player = self.state.get_unit(player_id)
        enemy = self.state.units.get(
            self.enemy_id if player_id == self.player_id else self.player_id
        )

        zoc = ZoneOfControlService(self.state)

        if enemy:
            dx = enemy.position[0] - player.position[0]
            dy = enemy.position[1] - player.position[1]
            distance = abs(dx) + abs(dy)
        else:
            dx = dy = distance = 0

        return {
            "my_strength": [player.strength],
            "enemy_strength": [enemy.strength if enemy else 0],
            "enemy_distance": [distance],
            "enemy_dx": [dx],
            "enemy_dy": [dy],
            "in_enemy_zoc": [int(zoc.is_hex_in_enemy_zoc(player, player.position))],
            "can_assault": [int(enemy is not None and distance == 1)],
        }