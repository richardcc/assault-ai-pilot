from __future__ import annotations


def load_state_dict(path, device: str) -> dict:
    import torch

    map_location = "cuda" if str(device).strip().lower() == "cuda" else "cpu"
    try:
        state = torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        state = torch.load(path, map_location=map_location)
    if isinstance(state, dict) and "state_dict" in state and isinstance(state["state_dict"], dict):
        state = state["state_dict"]
    if not isinstance(state, dict):
        raise TypeError(f"Unsupported checkpoint format at {path}")
    keys = list(state.keys())
    if keys and all(str(k).startswith("_orig_mod.") for k in keys):
        return {str(k)[10:]: v for k, v in state.items()}
    return state
