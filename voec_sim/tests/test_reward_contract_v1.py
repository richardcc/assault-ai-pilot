from voec_sim.core.simulator import VOECSimulator


def test_non_terminal_reward_is_zero_for_first_step():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1")
    action_id = sim.legal_actions()[0]
    transition = sim.step(action_id)
    if not transition.done:
        assert transition.reward == 0.0
