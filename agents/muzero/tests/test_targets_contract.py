from agents.muzero.core.targets import build_sample


def test_build_sample_shapes():
    sample = build_sample(
        observation=[0.0, 1.0, 2.0, 0.0],
        action_index=1,
        action_dim=3,
        reward=0.0,
        done=False,
    )
    assert len(sample.policy_target) == 3
    assert sample.policy_target[1] == 1.0
