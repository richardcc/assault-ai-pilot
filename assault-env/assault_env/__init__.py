from assault_env.scenario import simple_duel_scenario

from assault.core.actions.movement_action import MovementAction
from assault.core.actions.movement_executor import MovementExecutor
from assault.core.actions.assault_executor import AssaultExecutor
from assault.core.spatial.zone_of_control import ZoneOfControlService


class AssaultEnv:
    """
    Minimal training environment wrapping assault-engine.
    """

    def reset(self):
        """
        Resets the environment to the initial scenario.
        """
        self.state, self.player_id, self.enemy_id = simple_duel_scenario()
        self.done = False
        return self._get_obs()

    def step(self, action: int):
        """
        Executes one environment step.

        Actions:
            0 = WAIT
            1 = MOVE_FORWARD
            2 = ASSAULT
        """
        if self.done:
            raise RuntimeError("Episode already finished")

        reward = 0.0

        player = self.state.get_unit(self.player_id)
        enemy = self.state.get_unit(self.enemy_id)

        # ------------------------
        # Execute action
        # ------------------------

        if action == 1:  # MOVE_FORWARD
            executor = MovementExecutor(self.state)
            target = (player.position[0] + 1, player.position[1])
            try:
                executor.execute(MovementAction(player, target))
            except ValueError:
                reward -= 0.1  # invalid move penalty

        elif action == 2:  # ASSAULT
            executor = AssaultExecutor(self.state, self.player_id, self.enemy_id)
            report = executor.execute()
            reward += report.attacker_hits - report.defender_hits

        # ------------------------
        # Terminal conditions
        # ------------------------

        if not enemy.is_alive():
            reward += 5.0
            self.done = True

        if not player.is_alive():
            reward -= 5.0
            self.done = True

        return self._get_obs(), reward, self.done, {}

    def _get_obs(self):
        """
        Builds a minimal observation dictionary.
        """
        player = self.state.get_unit(self.player_id)
        enemy = self.state.get_unit(self.enemy_id)

        zoc = ZoneOfControlService(self.state)

        return {
            "my_strength": player.strength,
            "enemy_strength": enemy.strength,
            "in_enemy_zoc": zoc.is_hex_in_enemy_zoc(player, player.position),
            "can_assault": abs(player.position[0] - enemy.position[0]) == 1,
        }