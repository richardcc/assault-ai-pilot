from agents.muzero.objective_signals import objective_step_signal


def test_objective_signal_marks_opportunity_one_move_from_vp() -> None:
    before_units = [
        {"unit_id": "IT_1", "side": "IT", "alive": True, "q": 0, "r": 0},
    ]
    after_units = [
        {"unit_id": "IT_1", "side": "IT", "alive": True, "q": 1, "r": 0},
    ]
    vp_hexes = [{"vp_id": "VP_A", "q": 2, "r": 0}]
    signal = objective_step_signal(
        side="IT",
        vp_hexes=vp_hexes,
        legal_actions=["MOVE:IT_1:1:0"],
        before_units=before_units,
        before_vp_owner_by_hex={"2,0": "DE"},
        after_units=after_units,
        after_vp_owner_by_hex={"2,0": "DE"},
        legal_capture_options=0,
        capture_taken=False,
        vp_captures=0,
        vp_gain_for_side=0,
    )
    assert signal.objective_had_opportunity == 1
    assert signal.objective_min_dist_before == 2.0
    assert signal.objective_min_dist_after == 1.0
    assert signal.objective_progress_delta == 1.0
    assert signal.objective_best_vp_id == "VP_A"


def test_objective_signal_marks_conversion_on_capture() -> None:
    units = [{"unit_id": "IT_1", "side": "IT", "alive": True, "q": 2, "r": 0}]
    signal = objective_step_signal(
        side="IT",
        vp_hexes=[{"vp_id": "VP_A", "q": 2, "r": 0}],
        legal_actions=["CAPTURE:IT_1:2:0"],
        before_units=units,
        before_vp_owner_by_hex={"2,0": "DE"},
        after_units=units,
        after_vp_owner_by_hex={"2,0": "IT"},
        legal_capture_options=1,
        capture_taken=True,
        vp_captures=1,
        vp_gain_for_side=1,
    )
    assert signal.objective_had_opportunity == 1
    assert signal.objective_converted == 1
    assert signal.objective_min_dist_before == 0.0


def test_objective_signal_marks_opportunity_when_already_near_vp() -> None:
    units = [{"unit_id": "IT_1", "side": "IT", "alive": True, "q": 1, "r": 0}]
    signal = objective_step_signal(
        side="IT",
        vp_hexes=[{"vp_id": "VP_A", "q": 2, "r": 0}],
        legal_actions=["WAIT:IT_1"],
        before_units=units,
        before_vp_owner_by_hex={"2,0": "DE"},
        after_units=units,
        after_vp_owner_by_hex={"2,0": "DE"},
        legal_capture_options=0,
        capture_taken=False,
        vp_captures=0,
        vp_gain_for_side=0,
    )
    assert signal.objective_min_dist_before == 1.0
    assert signal.objective_progress_delta == 0.0
    assert signal.objective_had_opportunity == 1


def test_objective_signal_respects_opportunity_near_vp_threshold() -> None:
    units = [{"unit_id": "IT_1", "side": "IT", "alive": True, "q": 1, "r": 0}]
    signal = objective_step_signal(
        side="IT",
        vp_hexes=[{"vp_id": "VP_A", "q": 2, "r": 0}],
        legal_actions=["WAIT:IT_1"],
        before_units=units,
        before_vp_owner_by_hex={"2,0": "DE"},
        after_units=units,
        after_vp_owner_by_hex={"2,0": "DE"},
        legal_capture_options=0,
        capture_taken=False,
        vp_captures=0,
        vp_gain_for_side=0,
        opportunity_near_vp_max_dist=0.5,
    )
    assert signal.objective_min_dist_before == 1.0
    assert signal.objective_had_opportunity == 0
