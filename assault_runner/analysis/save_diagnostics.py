"""
Diagnostics and Replay Persistence Utilities.

Responsible for saving:
- Per-game engine diagnostics
- Series-level summaries
- Selected replays

This module does NOT run games.
"""

import json
from pathlib import Path
from typing import List, Dict


def normalize_for_json(obj):
    """
    Recursively convert NumPy scalars, arrays and containers
    to native Python types so they are JSON serializable.
    """
    import numpy as np

    if isinstance(obj, dict):
        return {k: normalize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [normalize_for_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return [normalize_for_json(v) for v in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    else:
        return obj


def save_series_results(
    *,
    output_dir: str,
    series_summary: Dict,
    game_diagnostics: List[Dict],
    replays: List[Dict],
) -> None:
    """
    Saves full results of a match series to disk.
    """

    base = Path(output_dir)
    diagnostics_dir = base / "diagnostics"
    replays_dir = base / "replays"

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    replays_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # Save series summary
    # --------------------------------------------------

    summary_path = diagnostics_dir / "series_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(normalize_for_json(series_summary), f, indent=2)

    # --------------------------------------------------
    # Save per-game diagnostics
    # --------------------------------------------------

    for idx, diag in enumerate(game_diagnostics, start=1):
        diag_path = diagnostics_dir / f"game_{idx:04d}_diag.json"
        with diag_path.open("w", encoding="utf-8") as f:
            json.dump(normalize_for_json(diag), f, indent=2)

    # --------------------------------------------------
    # Save replays
    # --------------------------------------------------

    for idx, replay in enumerate(replays, start=1):
        replay_path = replays_dir / f"game_{idx:04d}.json"
        with replay_path.open("w", encoding="utf-8") as f:
            json.dump(normalize_for_json(replay), f, indent=2)