from assault.replay.state import ReplayState, UnitState
from assault.replay.replay import Replay


def replay_state_from_dict(data: dict) -> ReplayState:
    """
    Convert a dict loaded from JSON into a ReplayState.
    """
    return ReplayState(
        turn=data["turn"],
        units=tuple(
            UnitState(
                unit_id=u["unit_id"],
                side=u["side"],
                hex=u["hex"],
                strength=u["strength"],
                status=u["status"],
            )
            for u in data["units"]
        ),
    )


def replay_from_dict(data: dict) -> Replay:
    """
    Convert a full replay dict into a Replay object.
    """
    states = [
        replay_state_from_dict(state_data)
        for state_data in data["states"]
    ]
    return Replay(states)
