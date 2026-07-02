from voec_sim.core.simulator import VOECSimulator


def test_timeout_resolution_marks_terminal_and_reason():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=1)
    tr = sim.resolve_timeout()
    assert tr.done is True
    assert tr.state.end_reason == "timeout_resolution"


def test_timeout_resolution_sets_winner_or_draw():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=2)
    tr = sim.resolve_timeout()
    assert tr.state.winner is None or isinstance(tr.state.winner, str)


def test_timeout_resolution_accepts_custom_reason():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=3)
    tr = sim.resolve_timeout(end_reason="scenario_turn_limit")
    assert tr.state.end_reason == "scenario_turn_limit"
