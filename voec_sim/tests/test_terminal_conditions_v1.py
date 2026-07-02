from voec_sim.core.simulator import VOECSimulator


def test_new_episode_starts_non_terminal():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1")
    assert sim.is_terminal() is False
