from dataclasses import dataclass
from typing import Dict


@dataclass
class SeriesOutcomeStats:
    """
    Tracks outcomes over a series of games.

    IMPORTANT:
    - episode_outcome.winner is expected to be:
        "A"   -> side A wins
        "B"   -> side B wins
        None  -> draw
    - VP are aggregated by side (A / B), never by nationality.
    """

    # --------------------------------------------------
    # Win / draw counts
    # --------------------------------------------------

    A_wins: int = 0
    B_wins: int = 0
    draws: int = 0

    # --------------------------------------------------
    # VP aggregation (final control of VP hexes)
    # --------------------------------------------------

    vp_A_total: int = 0
    vp_B_total: int = 0

    # --------------------------------------------------
    # Update
    # --------------------------------------------------

    def add(self, episode_outcome) -> None:
        """
        Add the result of one episode.

        episode_outcome.winner must be:
        - "A"  : side A wins
        - "B"  : side B wins
        - None : draw
        """

        winner = episode_outcome.winner

        if winner == "A":
            self.A_wins += 1
        elif winner == "B":
            self.B_wins += 1
        else:
            self.draws += 1

        # ✅ Accumulate VP (safe, side-based)
        self.vp_A_total += getattr(episode_outcome, "vp_A", 0)
        self.vp_B_total += getattr(episode_outcome, "vp_B", 0)

    # --------------------------------------------------
    # Aggregation
    # --------------------------------------------------

    def total_games(self) -> int:
        return self.A_wins + self.B_wins + self.draws

    def rates(self, total: int = None) -> Dict[str, float]:
        """
        Returns win/draw rates for the series.
        Keeps backward compatibility with older callers.
        """

        total = total or self.total_games()

        if total == 0:
            return {
                "A_win_rate": 0.0,
                "B_win_rate": 0.0,
                "draw_rate": 0.0,
            }

        return {
            "A_win_rate": self.A_wins / total,
            "B_win_rate": self.B_wins / total,
            "draw_rate": self.draws / total,
        }

    # --------------------------------------------------
    # Export
    # --------------------------------------------------

    def to_dict(self) -> Dict:
        total = self.total_games() or 1

        return {
            "A_wins": self.A_wins,
            "B_wins": self.B_wins,
            "draws": self.draws,
            "total_games": self.total_games(),

            # ✅ VP statistics (side-based, correct)
            "vp": {
                "avg_vp_A": self.vp_A_total / total,
                "avg_vp_B": self.vp_B_total / total,
            },
        }