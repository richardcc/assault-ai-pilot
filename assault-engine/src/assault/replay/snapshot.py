from assault.replay.state import ReplayState, UnitState

def snapshot(engine_state) -> ReplayState:
    """
    Create an immutable snapshot of the current engine state.
    Adapted to the real Unit model of the Assault engine.
    """

    return ReplayState(
        turn=getattr(engine_state, "turn", 0),
        units=tuple(
            UnitState(
                unit_id=unit.unit_id,
                side=unit.unit_id[0],           # 'A' or 'D'
                hex=str(unit.position),         # (q, r)
                strength=unit.strength,
                status=[s.name for s in unit.statuses],  # ✅ FIX
            )
            for unit in engine_state.units.values()
        ),
    )