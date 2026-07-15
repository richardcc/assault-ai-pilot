from agents.muzero.obs.contracts import (
    DecisionEvent,
    SearchEvent,
    TrainStepEvent,
    TransitionEvent,
)


def test_decision_event_payload_shape():
    payload = DecisionEvent(
        iteration=0,
        episode=0,
        step=1,
        chosen_action="A",
        top_actions=["A"],
        top_probs=[1.0],
    ).to_payload()
    assert payload["chosen_action"] == "A"


def test_train_step_event_payload_shape():
    payload = TrainStepEvent(
        iteration=0,
        loss=1.0,
        policy_loss=0.4,
        value_loss=0.3,
        reward_loss=0.3,
    ).to_payload()
    assert payload["loss"] == 1.0


def test_search_event_payload_shape():
    payload = SearchEvent(iteration=0, episode=0, step=0, node_count=10, max_depth=4).to_payload()
    assert payload["node_count"] == 10


def test_transition_event_payload_shape():
    payload = TransitionEvent(
        iteration=1,
        episode=2,
        step=3,
        game_turn=1,
        action_id="move:u1:0,0",
        to_play="A",
        reward_target=1.0,
        done=True,
        terminal_reason="max_steps",
        timeout=True,
        units_snapshot=[{"unit_id": "U1", "q": 0, "r": 0, "alive": True}],
    ).to_payload()
    assert payload["action_id"] == "move:u1:0,0"
    assert payload["units_snapshot"][0]["unit_id"] == "U1"
