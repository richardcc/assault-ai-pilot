from copy import deepcopy


def snapshot(state, decision=None, event=None):
    """
    Creates an immutable snapshot of the current GameState.

    Snapshots are used exclusively for offline analysis and replay.
    No mutation or interpretation occurs here.

    Supports:
    - agent decisions (decision)
    - system events (event: END_TURN, END_MATCH)
    """

    snap = {
        "state": {
            "units": {
                side: {
                    unit_id: unit.to_dict()
                    for unit_id, unit in units.items()
                }
                for side, units in state.units.items()
            },
            "vp_owner": {
                str(k): v
                for k, v in state.vp_owner.items()
            },
        }
    }

    if decision is not None:
        snap["decision"] = deepcopy(decision)

    # ✅ NEW: system-level structural event
    if event is not None:
        snap["event"] = event

    return snap
``