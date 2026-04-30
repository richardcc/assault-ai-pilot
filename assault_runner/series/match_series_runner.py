"""
Match Series Runner.

Executes multiple game sessions (e.g. 50 or 100 matches)
and aggregates outcomes and replays.

Engine diagnostics aggregation is handled externally
(by the offline_series_orchestrator).
"""

from typing import List, Dict

from assault_runner.session.game_session import GameSession
from assault_runner.analysis.series_outcome_stats import SeriesOutcomeStats


class MatchSeriesRunner:
    """
    Runs a series of games using ONLY policy_A (RL).

    Enemy heuristic is handled internally by AssaultEnv.
    """

    def __init__(
        self,
        *,
        scenario_id: str,
        policy_A,
        episodes: int,
        save_replays: int = 0,
        seed: int = 0,
        debug: bool = False,
        policy_B=None,  # legacy compatibility, ignored
    ):
        self.scenario_id = scenario_id
        self.policy_A = policy_A
        self.episodes = episodes
        self.save_replays = save_replays
        self.base_seed = seed
        self.debug = debug

        self.outcome_stats = SeriesOutcomeStats()
        self.replays: List[Dict] = []

    # --------------------------------------------------
    # Main execution
    # --------------------------------------------------

    def run(self) -> Dict:
        """
        Executes the full match series.
        """

        games: List[Dict] = []

        for i in range(self.episodes):
            episode_seed = self.base_seed + i
            collect_replay = i < self.save_replays

            session = GameSession(
                scenario_id=self.scenario_id,
                policy_A=self.policy_A,
                seed=episode_seed,
                collect_replay=collect_replay,
                debug=self.debug,
            )

            result = session.run()

            # Aggregate outcomes
            self.outcome_stats.add(result.outcome)

            # Store replay frames
            games.append({
                "frames": result.replay["frames"]
                if result.replay is not None
                else []
            })

            # Store replay data if requested
            if collect_replay and result.replay is not None:
                self.replays.append(result.replay)

        total = self.episodes

        return {
            "games": games,
            "outcomes": self.outcome_stats.to_dict(),
            "rates": self.outcome_stats.rates(total),
            "replays": self.replays,
        }