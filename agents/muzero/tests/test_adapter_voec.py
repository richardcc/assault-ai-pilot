from agents.muzero.adapter_voec import MuZeroVOECAdapter
from voec_sim.core.simulator import VOECSimulator


def test_adapter_initial_state_and_legal_actions():
    adapter = MuZeroVOECAdapter(VOECSimulator())
    obs = adapter.initial_state("battaglia_cittadina_2_1", seed=3)
    assert obs.turn >= 1
    assert adapter.legal_actions()
