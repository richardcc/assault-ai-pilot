from voec_sim.core.simulator import VOECSimulator
from voec_sim.ui_contract.events import SCHEMA_VERSION, EpisodeTimeline, TransitionEvent
from voec_sim.ui_contract.timeline import build_episode_timeline


def test_transition_event_schema_version_is_stable():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1")
    action_id = sim.legal_actions()[0]
    tr = sim.step(action_id)
    evt = TransitionEvent.from_snapshot(tr.state, tr.action_id, tr.reward, tr.done)
    assert evt.schema_version == SCHEMA_VERSION


def test_episode_timeline_contains_transitions():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=42)
    action_id = sim.legal_actions()[0]
    tr = sim.step(action_id)
    evt = TransitionEvent.from_snapshot(tr.state, tr.action_id, tr.reward, tr.done)
    timeline = EpisodeTimeline(
        schema_version=SCHEMA_VERSION,
        scenario_id="battaglia_cittadina_2_1",
        seed=42,
        transitions=[evt.to_dict()],
    )
    assert len(timeline.transitions) == 1


def test_build_episode_timeline_runs_with_policy_fn():
    sim = VOECSimulator()

    def first_legal(legal_actions):
        return legal_actions[0]

    timeline = build_episode_timeline(
        sim=sim,
        scenario_id="battaglia_cittadina_2_1",
        seed=7,
        policy_fn=first_legal,
        max_steps=5,
    )
    assert timeline.schema_version == SCHEMA_VERSION
    assert timeline.scenario_id == "battaglia_cittadina_2_1"
    assert 1 <= len(timeline.transitions) <= 5
