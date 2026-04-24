import gymnasium as gym
from gymnasium import spaces

from assault_env.agents.heuristic import HeuristicAgent

from assault.core.actions.movement_action import MovementAction
from assault.core.actions.movement_executor import MovementExecutor
from assault.core.actions.assault_executor import AssaultExecutor
from assault.core.spatial.zone_of_control import ZoneOfControlService


class AssaultEnv(gym.Env):
    """
    Gymnasium environment for assault-engine.

    Supports:
    - P1: single controlled unit
    - P2: multiple controlled units
    - P3: global force awareness
    - P4: symmetric engagement (2 vs 2)
    - B: implicit role emergence
    """

    metadata = {"render_modes": ["ascii"]}

    def __init__(
        self,
        scenario_builder,
        training: bool = True,
        max_turns: int = 200,
    ):
        super().__init__()

        self.training = training
        self.max_turns = max_turns

        # --------------------------------------------------------
        # Action space
        # --------------------------------------------------------
        self.action_space = spaces.Discrete(7)

        # --------------------------------------------------------
        # Observation space (P4 + Roles Implícitos)
        # --------------------------------------------------------
        self.observation_space = spaces.Dict({
            "my_strength": spaces.Box(0, 20, (1,), int),
            "enemy_strength": spaces.Box(0, 20, (1,), int),
            "enemy_distance": spaces.Box(0, 50, (1,), int),
            "enemy_dx": spaces.Box(-50, 50, (1,), int),
            "enemy_dy": spaces.Box(-50, 50, (1,), int),
            "in_enemy_zoc": spaces.Box(0, 1, (1,), int),
            "can_assault": spaces.Box(0, 1, (1,), int),

            # Global force awareness (P3)
            "my_total_strength": spaces.Box(0, 100, (1,), int),
            "enemy_total_strength": spaces.Box(0, 100, (1,), int),

            # ✅ Roles implícitos (B)
            "ally_distance": spaces.Box(0, 50, (1,), int),
            "ally_strength_diff": spaces.Box(-20, 20, (1,), int),
        })

        self.scenario_builder = scenario_builder

        self.heuristic = HeuristicAgent(
            epsilon=0.3 if training else 0.0
        )

        self.state = None
        self.italy_ids = []
        self.enemy_ids = []

        self.current_side = "italy"
        self.current_italy_index = 0

        self.turn_count = 0
        self.done = False

        # Victory Points
        self.VP_HEXES = {
            (3, 4): 2,
            (5, 5): 2,
            (2, 8): 2,
        }
        self.vp_controlled = set()

        # Metrics
        self.metric_steps = 0
        self.metric_moves = 0
        self.metric_waits = 0
        self.metric_assaults = 0
        self.metric_distance_sum = 0.0
        self.metric_vp_points = 0

    # ------------------------------------------------------------
    # RESET
    # ------------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.state, self.italy_ids, self.enemy_ids = self.scenario_builder()

        self.current_side = "italy"
        self.current_italy_index = 0
        self.turn_count = 0
        self.done = False

        self.vp_controlled.clear()

        self.metric_steps = 0
        self.metric_moves = 0
        self.metric_waits = 0
        self.metric_assaults = 0
        self.metric_distance_sum = 0.0
        self.metric_vp_points = 0

        return self._get_obs(), {}

    # ------------------------------------------------------------
    # STEP
    # ------------------------------------------------------------

    def step(self, action: int):
        if self.done:
            raise RuntimeError("Episode already finished")

        self.metric_steps += 1

        # Select active unit
        if self.current_side == "italy":
            actor_id = self._next_alive_italy()
        else:
            alive_enemies = [
                eid for eid in self.enemy_ids if eid in self.state.units
            ]
            if not alive_enemies:
                return self._get_obs(), 0.0, True, False, {}
            actor_id = alive_enemies[0]

        actor = self.state.units.get(actor_id)

        # Enemy heuristic
        if self.current_side == "enemy":
            observation = self._get_obs()
            alive_italians = [
                uid for uid in self.italy_ids if uid in self.state.units
            ]
            player_pos = (
                self.state.units[alive_italians[0]].position
                if alive_italians else actor.position
            )

            action = self.heuristic.act(
                observation,
                enemy_pos=actor.position,
                player_pos=player_pos,
                vp_hexes=self.VP_HEXES.keys(),
                vp_controlled_by_player=self.vp_controlled,
            )

        reward = 0.0
        terminated = False
        truncated = False

        enemy_ids = (
            self.enemy_ids if self.current_side == "italy"
            else self.italy_ids
        )
        enemy = next(
            (self.state.units[eid] for eid in enemy_ids if eid in self.state.units),
            None
        )

        prev_distance = (
            abs(enemy.position[0] - actor.position[0]) +
            abs(enemy.position[1] - actor.position[1])
            if enemy else 0
        )
        self.metric_distance_sum += prev_distance

        executor = MovementExecutor(self.state)

        # WAIT
        if action == 0:
            self.metric_waits += 1
            reward -= 0.05

        # MOVEMENT
        target = None
        if action == 1:
            target = (actor.position[0] + 1, actor.position[1])
        elif action == 4:
            target = (actor.position[0], actor.position[1] + 1)
        elif action == 5:
            target = (actor.position[0], actor.position[1] - 1)
        elif action == 6:
            target = (actor.position[0] - 1, actor.position[1])

        if target is not None:
            try:
                executor.execute(MovementAction(actor, target))
                self.metric_moves += 1
                reward += 0.01
            except ValueError:
                reward -= 0.1

        # ASSAULT
        if action == 2 and enemy:
            self.metric_assaults += 1
            if prev_distance > 1:
                reward -= 0.2
            else:
                eb = enemy.strength
                pb = actor.strength
                AssaultExecutor(
                    self.state,
                    actor.unit_id,
                    enemy.unit_id,
                ).execute()
                ea = enemy.strength if enemy.unit_id in self.state.units else 0
                reward += (eb - ea) - (pb - actor.strength)

        # VP control
        pos = actor.position
        if pos in self.VP_HEXES:
            if pos not in self.vp_controlled:
                self.vp_controlled.add(pos)
                reward += 0.4
            reward += 0.2
        else:
            if self.vp_controlled:
                reward -= 0.3
                self.vp_controlled.clear()

        self.metric_vp_points = len(self.vp_controlled) * 2

        # Termination
        if not any(eid in self.state.units for eid in self.enemy_ids):
            terminated = True
            reward += 5.0

        if not any(uid in self.state.units for uid in self.italy_ids):
            terminated = True
            reward -= 5.0

        self._rotate_turn()

        self.turn_count += 1
        if self.turn_count >= self.max_turns and not terminated:
            truncated = True
            vp = self.metric_vp_points
            reward += 10.0 if vp >= 4 else (2.0 if vp == 3 else -5.0)
            self.done = True

        info = {}
        if terminated or truncated:
            info["metrics"] = {
                "steps": self.metric_steps,
                "moves": self.metric_moves,
                "waits": self.metric_waits,
                "assaults": self.metric_assaults,
                "avg_distance": (
                    self.metric_distance_sum / self.metric_steps
                    if self.metric_steps > 0 else 0.0
                ),
                "vp_points": self.metric_vp_points,
            }

        return self._get_obs(), reward, terminated, truncated, info

    # ------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------

    def _next_alive_italy(self):
        for _ in range(len(self.italy_ids)):
            uid = self.italy_ids[self.current_italy_index]
            self.current_italy_index = (
                self.current_italy_index + 1
            ) % len(self.italy_ids)
            if uid in self.state.units:
                return uid
        return self.italy_ids[0]

    def _rotate_turn(self):
        self.current_side = (
            "enemy" if self.current_side == "italy" else "italy"
        )

    def _get_obs(self):
        if self.current_side == "italy":
            uid = self._next_alive_italy()
        else:
            alive_enemies = [
                eid for eid in self.enemy_ids if eid in self.state.units
            ]
            if not alive_enemies:
                return self._empty_obs()
            uid = alive_enemies[0]

        if uid not in self.state.units:
            return self._empty_obs()

        player = self.state.units[uid]

        enemy_ids = (
            self.enemy_ids if self.current_side == "italy"
            else self.italy_ids
        )
        enemy = next(
            (self.state.units[eid] for eid in enemy_ids if eid in self.state.units),
            None
        )

        # Global force
        my_total_strength = sum(
            u.strength for uid, u in self.state.units.items()
            if uid in self.italy_ids
        )
        enemy_total_strength = sum(
            u.strength for uid, u in self.state.units.items()
            if uid in self.enemy_ids
        )

        # --- Ally info (roles implícitos) ---
        ally_units = [
            u for uid, u in self.state.units.items()
            if uid in self.italy_ids and uid != player.unit_id
        ]

        if ally_units:
            ally = ally_units[0]
            ally_dist = (
                abs(ally.position[0] - player.position[0]) +
                abs(ally.position[1] - player.position[1])
            )
            ally_strength_diff = player.strength - ally.strength
        else:
            ally_dist = 0
            ally_strength_diff = 0

        zoc = ZoneOfControlService(self.state)

        dx = dy = dist = 0
        if enemy:
            dx = enemy.position[0] - player.position[0]
            dy = enemy.position[1] - player.position[1]
            dist = abs(dx) + abs(dy)

        return {
            "my_strength": [player.strength],
            "enemy_strength": [enemy.strength if enemy else 0],
            "enemy_distance": [dist],
            "enemy_dx": [dx],
            "enemy_dy": [dy],
            "in_enemy_zoc": [
                int(zoc.is_hex_in_enemy_zoc(player, player.position))
            ],
            "can_assault": [int(enemy is not None and dist == 1)],
            "my_total_strength": [my_total_strength],
            "enemy_total_strength": [enemy_total_strength],
            "ally_distance": [ally_dist],
            "ally_strength_diff": [ally_strength_diff],
        }

    @staticmethod
    def _empty_obs():
        return {
            "my_strength": [0],
            "enemy_strength": [0],
            "enemy_distance": [0],
            "enemy_dx": [0],
            "enemy_dy": [0],
            "in_enemy_zoc": [0],
            "can_assault": [0],
            "my_total_strength": [0],
            "enemy_total_strength": [0],
            "ally_distance": [0],
            "ally_strength_diff": [0],
        }