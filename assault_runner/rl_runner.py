"""
RLRunner: execution of a full game driven by a trained RL agent.

Responsibilities:
- Run one complete episode in AssaultEnv
- Capture each step as a ReplayState
- Build a Replay compatible with assault-viewer
- Persist the replay to JSON

Does NOT:
- Train agents
- Render anything
- Modify engine rules
"""

from typing import List

from stable_baselines3 import PPO

from assault_env.env import AssaultEnv
from assault_env.scenario_base import simple_duel_level7_P4_2v2_from_json

from assault.replay.replay import Replay
from assault.replay.state import ReplayState, UnitState
from assault.replay.serialization import save_replay_to_json


class RLRunner:
    """
    Runner that executes a trained PPO agent and records a Replay.
    """

    def run_episode(
        self,
        model_path: str,
        output_path: str,
        deterministic: bool = False,
        max_turns: int = 200,
    ):
        """
        Execute one episode and save it as a replay JSON.
        """

        env = AssaultEnv(
            scenario_builder=simple_duel_level7_P4_2v2_from_json,
            training=False,
            max_turns=max_turns,
        )

        model = PPO.load(model_path)

        obs, _ = env.reset()

        replay_states: List[ReplayState] = []
        terminated = False
        truncated = False
        turn = 0

        while not (terminated or truncated):
            turn += 1

            # Capture state BEFORE action
            replay_states.append(self._capture_state(env, turn))

            action, _ = model.predict(obs, deterministic=deterministic)
            obs, _, terminated, truncated, _ = env.step(action)

        # ✅ Engine Replay expects ONLY a list of ReplayState
        replay = Replay(replay_states)

        save_replay_to_json(replay, output_path)
        print(f"[RLRunner] Replay saved to: {output_path}")

    # ------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------

    def _capture_state(self, env: AssaultEnv, turn: int) -> ReplayState:
        """
        Convert engine state into a ReplayState.
        """

        units: List[UnitState] = []

        for u in env.state.units.values():
            units.append(
                UnitState(
                    unit_id=u.unit_id,
                    side=self._map_side(u),
                    hex=self._pos_to_hex(u.position),
                    strength=u.strength,
                    status=self._extract_statuses(u),
                )
            )

        return ReplayState(
            turn=turn,
            units=units,
        )

    def _map_side(self, unit) -> str:
        """
        Map engine unit to replay side (A / B).
        Purely for visualization.
        """

        if unit.unit_id.startswith(("IT", "US", "A")):
            return "A"
        else:
            return "B"

    def _extract_statuses(self, unit) -> List[str]:
        """
        Extract unit statuses defensively.
        """

        if hasattr(unit, "statuses"):
            return list(unit.statuses)

        if hasattr(unit, "status"):
            return list(unit.status)

        return []

    def _pos_to_hex(self, position) -> str:
        """
        Convert engine (col, row) to hex string like 'C5'.
        """

        col, row = position
        col_letter = chr(ord("A") + col)
        return f"{col_letter}{row + 1}"