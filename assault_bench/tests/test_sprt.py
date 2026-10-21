# -*- coding: utf-8 -*-
"""Unit tests for Wald's Sequential Probability Ratio Test (SPRT)."""

from assault_bench.sprt import WaldSPRT


def test_sprt_initialization_thresholds():
    sprt = WaldSPRT(p0=0.50, p1=0.75, alpha=0.01, beta=0.01, min_games=10)
    assert sprt.bound_a > 4.0
    assert sprt.bound_b < -4.0
    assert sprt.total_games == 0
    assert sprt.win_rate == 0.0


def test_sprt_dominant_streak_triggers_early_pass():
    sprt = WaldSPRT(p0=0.50, p1=0.75, alpha=0.01, beta=0.01, min_games=10)
    # Win 12 games in a row
    dec = None
    for i in range(12):
        dec = sprt.record_result(win=True)
    assert dec is not None
    assert dec.should_stop is True
    assert dec.decision == "accept_h1"
    assert dec.games_played == 12
    assert dec.win_rate == 1.0


def test_sprt_losing_streak_triggers_early_fail():
    sprt = WaldSPRT(p0=0.50, p1=0.75, alpha=0.01, beta=0.01, min_games=10)
    # Lose 10 games in a row
    dec = None
    for i in range(10):
        dec = sprt.record_result(win=False, loss=True)
    assert dec is not None
    assert dec.should_stop is True
    assert dec.decision == "accept_h0"
    assert dec.win_rate == 0.0


def test_sprt_respects_min_games_guard():
    sprt = WaldSPRT(p0=0.50, p1=0.75, alpha=0.01, beta=0.01, min_games=15)
    for _ in range(5):
        dec = sprt.record_result(win=True)
        assert dec.should_stop is False
        assert "gathering_minimum_samples" in dec.reason
