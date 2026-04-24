# Running and Reproducing the Project

This file contains the **canonical commands** to build documentation,
run a trained agent, generate replays, convert them for visualization,
and inspect them using the available viewers.

All commands are intended to be executed from the **project root**
unless explicitly stated otherwise.

---

## 1. Build Documentation (Sphinx)

Build the unified HTML documentation using Sphinx:

```bash
sphinx-build -b html docs docs/_build/html
```

Open the generated documentation:

```
docs/_build/html/index.html
```

---

## 2. Run a Trained Agent and Generate an Engine Replay

This command executes a trained PPO agent and records a replay
directly from the engine state.

The replay generated at this step is a **state-based engine replay**
(snapshot per turn), intended for reproducibility and analysis.

```bash
python -c "from assault_runner.rl_runner import RLRunner
RLRunner().run_episode(
    model_path='models/ppo_level7_p4_2v2_roles',
    output_path='replays/sample_engine_replay.json',
    deterministic=False
)
"
```

### Notes

- `deterministic=False` enables stochastic policy execution.
- The output is a **state snapshot replay**, not an event-based replay.
- This format is produced by the engine and must not be modified.

---

## 3. Visualize Engine Replay (Python Viewer)

The Python viewer consumes the engine replay format directly.

Change to the viewer scripts directory:

```bash
cd assault-viewer/scripts
```

Run the viewer:

```bash
python replay_viewer.py ..\..
eplays\sample_engine_replay.json
```

### Viewer capabilities

- Hex-grid terrain rendering (S2 / S3 layers)
- Unit counters and stacking
- Camera pan and zoom
- Step-by-step playback
- Deterministic reproduction of engine behavior

---

## 4. Convert Engine Replay to Web Replay Format

The web viewer does **not** consume engine replays directly.

An explicit conversion step produces an **event-based replay**
suitable for visualization, history inspection, and explanation.

```bash
python scripts/convert_replay_to_web.py     replays/sample_engine_replay.json     assault-web/data/replay_demo.json
```

### Notes

- This step is **offline** and reproducible.
- The converter infers events (MOVE, ATTACK, HOLD) from state transitions.
- The engine replay format remains unchanged.

---

## 5. Open the Web Replay Viewer

The web viewer is a standalone application that consumes:

- Web replay JSON
- Unit definitions
- Brigade definitions
- Static assets

Open the file:

```
assault-web/index.html
```

(serve via a local static server if required by the browser).

### Web viewer capabilities

- Replay playback (forward / backward)
- Historical movement per unit
- Active unit highlighting
- Unit card display (weapons, cost, capabilities, restrictions)
- Foundation for explanation and NLP chat (post-hoc)

---

## 6. Typical Workflow Summary

A standard workflow looks like this:

1. (Optional) Build documentation
2. Run agent to generate an engine replay
3. Inspect replay with Python viewer (optional)
4. Convert replay to web format
5. Inspect replay using the web viewer

---

## 7. Environment Assumptions

- A single virtual environment exists at the project root (`.venv`)
- Dependencies are installed via `requirements.txt`
- No module-local virtual environments are used
- Engine replays and web replays use **different formats by design**

---

## 8. Source of Truth

This file is the **only authoritative reference** for:

- execution
- replay generation
- replay conversion
- visualization workflows
