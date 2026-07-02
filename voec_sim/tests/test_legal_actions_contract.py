from voec_sim.core.simulator import VOECSimulator


def test_legal_actions_returns_non_empty_string_ids():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1")
    actions = sim.legal_actions()
    assert actions
    assert all(isinstance(a, str) and a for a in actions)


def test_pending_reaction_exposes_explicit_reaction_actions():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1")
    runtime = sim._runtime
    assert runtime is not None
    runtime.pending_reaction = {
        "reactor_id": "IT_1",
        "target_id": "US_1",
        "trigger": "ENEMY_MOVES_IN_LOS",
    }
    actions = sim.legal_actions()
    assert "OPPORTUNITY_FIRE:IT_1:US_1" in actions
    assert "OPPORTUNITY_SKIP:IT_1:US_1" in actions
