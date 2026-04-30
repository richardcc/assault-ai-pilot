"""
Game Session.

Executes a single Assault match and returns outcome + replay.
"""

from assault_env.env import AssaultEnv
from assault_runner.analysis.episode_outcomes import EpisodeOutcome


class GameSessionResult:
    def __init__(self, *, outcome, replay):
        self.outcome = outcome
        self.replay = replay


class GameSession:
    """
    Executes one complete game session.

    IMPORTANT:
    - Uses ONLY policy_A (RL)
    - Enemy heuristic is handled INSIDE AssaultEnv
    """

    def __init__(
        self,
        *,
        scenario_id: str,
        policy_A,
        seed: int,
        collect_replay: bool,
        debug: bool = False,
    ):
        self.scenario_id = scenario_id
        self.policy_A = policy_A
        self.seed = seed
        self.collect_replay = collect_replay
        self.debug = debug

    def run(self) -> GameSessionResult:
        env = AssaultEnv(
            scenario_id=self.scenario_id,
            rl_side="A",
            seed=self.seed,
            debug=self.debug,
        )

        obs, info = env.reset(seed=self.seed)
        done = False
        frames = []

        while not done:
            action = int(self.policy_A.act(obs))
            obs, _, terminated, truncated, info = env.step(action)

            for frame in info.get("frames", []):
                frames.append(frame)

            done = terminated or truncated

        replay = {"frames": frames} if self.collect_replay else None

        # --------------------------------------------------
        # Extract final VP from END_MATCH frame
        # --------------------------------------------------
        vp_A = 0
        vp_B = 0

        for frame in reversed(frames):
            if frame.get("event") == "END_MATCH":
                vp_A = frame.get("vp_A", 0)
                vp_B = frame.get("vp_B", 0)
                break

        # --------------------------------------------------
        # ✅ Correct winner determination
        # --------------------------------------------------
        alive_sides = [
            side
            for side, units in env.state.units.items()
            if any(u.is_alive() for u in units.values())
        ]

        if len(alive_sides) == 1:
            # Victory by elimination
            winner = alive_sides[0]
        else:
            # Victory by VP (or draw)
            if vp_A > vp_B:
                winner = "A"
            elif vp_B > vp_A:
                winner = "B"
            else:
                winner = None  # draw

        outcome = EpisodeOutcome(
            winner=winner,
            vp_A=vp_A,
            vp_B=vp_B,
            total_turns=env.current_round,
        )

        return GameSessionResult(
            outcome=outcome,
            replay=replay,
        )