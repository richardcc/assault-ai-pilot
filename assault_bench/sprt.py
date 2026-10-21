# -*- coding: utf-8 -*-
"""Wald's Sequential Probability Ratio Test (SPRT) for RL Benchmarking (Task 2.9).

Enables statistically rigorous early termination in benchmark evaluations
(standard in AlphaZero, Stockfish, LCZero, and KataGo).
Prevents running redundant episodes when candidate policy superiority (H1)
or inferiority (H0) is mathematically proven at significance alpha (e.g., 0.01).
"""

from __future__ import annotations

import math
from typing import NamedTuple


class SPRTDecision(NamedTuple):
    should_stop: bool
    decision: str  # "continue", "accept_h1" (pass), "accept_h0" (fail)
    llr: float
    bound_a: float
    bound_b: float
    games_played: int
    win_rate: float
    reason: str


class WaldSPRT:
    """Sequential Probability Ratio Test for Bernoulli/Tri-state trials."""

    def __init__(
        self,
        p0: float = 0.50,
        p1: float = 0.75,
        alpha: float = 0.01,
        beta: float = 0.01,
        min_games: int = 12,
        max_games: int = 100,
    ) -> None:
        if not (0.0 < p0 < p1 < 1.0):
            raise ValueError(f"Invalid probabilities: 0 < p0 ({p0}) < p1 ({p1}) < 1.0 required")
        if not (0.0 < alpha < 0.5 and 0.0 < beta < 0.5):
            raise ValueError(f"Invalid error rates: alpha={alpha}, beta={beta}")

        self.p0 = float(p0)
        self.p1 = float(p1)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.min_games = max(2, int(min_games))
        self.max_games = max(self.min_games, int(max_games))

        # Wald decision thresholds:
        # A = ln((1 - beta) / alpha)
        # B = ln(beta / (1 - alpha))
        self.bound_a = math.log((1.0 - beta) / alpha)
        self.bound_b = math.log(beta / (1.0 - alpha))

        # Log increments per outcome
        self._llr_win = math.log(self.p1 / self.p0)
        self._llr_loss = math.log((1.0 - self.p1) / (1.0 - self.p0))
        self._llr_draw = 0.5 * (self._llr_win + self._llr_loss)

        self.llr: float = 0.0
        self.wins: int = 0
        self.losses: int = 0
        self.draws: int = 0

    @property
    def total_games(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return (float(self.wins) + 0.5 * float(self.draws)) / float(self.total_games)

    def record_result(self, win: bool, loss: bool = False, draw: bool = False) -> SPRTDecision:
        """Record game outcome and evaluate Wald stopping criteria."""
        if win:
            self.wins += 1
            self.llr += self._llr_win
        elif loss or (not win and not draw):
            self.losses += 1
            self.llr += self._llr_loss
        else:
            self.draws += 1
            self.llr += self._llr_draw

        n = self.total_games
        wr = self.win_rate

        # Guard minimum sample size before declaring early victory/defeat
        if n < self.min_games:
            return SPRTDecision(
                should_stop=False,
                decision="continue",
                llr=self.llr,
                bound_a=self.bound_a,
                bound_b=self.bound_b,
                games_played=n,
                win_rate=wr,
                reason=f"gathering_minimum_samples ({n}/{self.min_games})",
            )

        if self.llr >= self.bound_a:
            return SPRTDecision(
                should_stop=True,
                decision="accept_h1",
                llr=self.llr,
                bound_a=self.bound_a,
                bound_b=self.bound_b,
                games_played=n,
                win_rate=wr,
                reason=f"SPRT accept H1 (LLR={self.llr:.2f} >= {self.bound_a:.2f}, win_rate={wr:.1%})",
            )

        if self.llr <= self.bound_b:
            return SPRTDecision(
                should_stop=True,
                decision="accept_h0",
                llr=self.llr,
                bound_a=self.bound_a,
                bound_b=self.bound_b,
                games_played=n,
                win_rate=wr,
                reason=f"SPRT accept H0 (LLR={self.llr:.2f} <= {self.bound_b:.2f}, win_rate={wr:.1%})",
            )

        if n >= self.max_games:
            return SPRTDecision(
                should_stop=True,
                decision="max_games_reached",
                llr=self.llr,
                bound_a=self.bound_a,
                bound_b=self.bound_b,
                games_played=n,
                win_rate=wr,
                reason=f"SPRT reached max games limit ({n}/{self.max_games})",
            )

        return SPRTDecision(
            should_stop=False,
            decision="continue",
            llr=self.llr,
            bound_a=self.bound_a,
            bound_b=self.bound_b,
            games_played=n,
            win_rate=wr,
            reason=f"continue_sampling (B={self.bound_b:.2f} < LLR={self.llr:.2f} < A={self.bound_a:.2f})",
        )
