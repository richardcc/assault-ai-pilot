"""
RLRunner: execution of a single game driven by a trained RL agent.

Responsibilities:
- Run ONE complete game using GameSession
- Capture replay compatible with assault-viewer
- Persist replay JSON

IMPORTANT SEMANTICS:
- Agent decisions are stored as ACTION frames
- Structural game events (END_TURN / END_MATCH)
  are emitted by the engine and forwarded transparently

Does NOT:
- Train agents
- Analyze statistics
- Modify engine rules
"""

from stable_baselines3 import PPO

from assault_runner.session.game_session import GameSession
from assault_runner.policies import ExplainableActorCriticPolicy
from assault.replay.replay import Replay
from assault.replay.serialization import save_replay_to_json


class RLPolicyAdapter:
    """
    Adapter to make a PPO model compatible with GameSession.
    """

    def __init__(self, model_path: str, deterministic: bool = False):
        # Load PPO model with custom policy class
        self.model = PPO.load(
            model_path,
            custom_objects={
                "policy_class": ExplainableActorCriticPolicy
            }
        )
        self.deterministic = deterministic
        self.name = "RL"

    def act(self, obs):
        action, _ = self.model.predict(
            obs,
            deterministic=self.deterministic
        )
        return action


class RLRunner:
    """
    Runs a single RL-vs-heuristic game and stores replay.

    NOTES:
    - Enemy is handled internally by AssaultEnv (HeuristicEnemy)
    - This runner does NOT inject opponent policies
    - END_TURN and END_MATCH are SYSTEM EVENTS
    """

    def run_episode(
        self,
        *,
        model_path: str,
        scenario_id: str,
        output_path: str,
        deterministic: bool = False,
        seed: int = 0,
    ):
        """
        Execute one episode and save it as replay JSON.
        """

        rl_policy = RLPolicyAdapter(
            model_path=model_path,
            deterministic=deterministic,
        )

        # ✅ GameSession uses ONLY policy_A
        session = GameSession(
            scenario_id=scenario_id,
            policy_A=rl_policy,
            seed=seed,
            collect_replay=True,
        )

        result = session.run()

        # --------------------------------------------
        # Convert GameSession replay to engine Replay
        # --------------------------------------------

        replay = Replay.from_dict(result.replay)

        # Defensive check
        if not replay.frames:
            raise RuntimeError(
                "Replay is empty: episode did not execute correctly."
            )

        save_replay_to_json(replay, output_path)

        print(f"[RLRunner] Replay saved to: {output_path}")

        return result