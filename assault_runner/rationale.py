# assault_runner/rationale.py

"""
Rationale utilities.

IMPORTANT DESIGN DECISION
-------------------------
There are TWO sources of rationales in the system:

1) PRIMARY (during PPO training & evaluation):
   - Produced by the policy via an auxiliary head
   - Used by RationaleLossCallback
   - Extracted from ExplainableActorCriticPolicy.last_rationale_logits

2) SECONDARY / FALLBACK (deterministic, post-hoc):
   - Derived from state transitions
   - Used only for analysis, legacy replay, or baseline comparison
"""

from assault.core.rationale import Rationale


# ==================================================
# PRIMARY: policy-based rationale (preferred)
# ==================================================

def decode_rationale_from_logits(logits):
    """
    Convert policy-produced rationale logits into a discrete Rationale.

    Args:
        logits (torch.Tensor): shape (batch, n_rationales)

    Returns:
        Rationale | None
    """
    if logits is None:
        return None

    try:
        import torch
        idx = torch.argmax(logits, dim=-1).item()
        return Rationale(idx)
    except Exception:
        return None


# ==================================================
# SECONDARY: deterministic post-hoc inference
# ==================================================

def infer_rationale(prev_state, next_state, unit_id):
    """
    Deterministic, post-hoc tactical rationale.

    ⚠️ NOT USED FOR TRAINING
    ⚠️ DOES NOT INSPECT THE AGENT
    ⚠️ KEPT ONLY FOR:
        - legacy replays
        - comparisons with learned rationales
        - debugging / analysis
    """

    # Unit lookup
    u0 = prev_state.get_unit(unit_id)
    u1 = next_state.get_unit(unit_id)

    # Unit missing or invalid
    if u0 is None or u1 is None:
        return Rationale.WAIT

    # No movement
    if u0.hex == u1.hex:
        return Rationale.WAIT

    # Distance to nearest enemy (domain semantics)
    d0 = prev_state.distance_to_nearest_enemy(u0)
    d1 = next_state.distance_to_nearest_enemy(u1)

    # Moved closer to enemy
    if d1 < d0:
        return Rationale.ADVANCE_TO_CONTACT

    # Moved away from enemy
    if d1 > d0:
        return Rationale.REPOSITION

    return Rationale.WAIT