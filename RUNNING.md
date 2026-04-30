RUNNING and Reproducing the Project
==================================

This document is the canonical reference for running, reproducing,
evaluating, and debugging the Assault‑Env project.

It defines the supported commands and workflows to:

- build and publish documentation
- train reinforcement learning agents
- run trained agents
- generate and visualize replays
- execute offline batch evaluations (50 / 100 / N games)
- collect engine‑level diagnostics
- debug tactical behavior and engine dynamics

All commands must be executed from the project root
unless explicitly stated otherwise.

------------------------------------------------------------
1. Environment Assumptions
------------------------------------------------------------

- A single virtual environment exists at the project root (.venv)
- Python version: 3.10+
- Dependencies installed via pyproject.toml / pip
- No module‑local virtual environments are used
- The project root is the working directory when executing commands

------------------------------------------------------------
2. Build Documentation (Sphinx, Local)
------------------------------------------------------------

Build the unified HTML documentation:

sphinx-build -b html docs docs/_build/html

Open the generated documentation:

docs/_build/html/index.html

Notes:
- This builds documentation locally only
- It does not publish anything to GitHub Pages
- Safe to run at any time while working on main

------------------------------------------------------------
3. Publish Documentation to GitHub Pages (Canonical)
------------------------------------------------------------

Documentation publication is handled exclusively by:

publish-docs.ps1

This script must be executed from the project root.

Command:

publish-docs.ps1

What the script does:

- verifies the working tree is clean
- verifies or switches to the main branch
- builds the Sphinx HTML documentation
- publishes via a dedicated git worktree
- commits and pushes only to gh-pages
- aborts if any validation fails

Rules:

- All development happens on main
- gh-pages is never edited manually
- Documentation is never published by hand
- If publication fails, no remote state is modified

publish-docs.ps1 is the only supported publication method.

------------------------------------------------------------
4. Train a Reinforcement Learning Agent
------------------------------------------------------------

Train an explainable PPO agent using the tactical engine environment:

python assault-env/train/train.py

Notes:
- Model snapshots are written to models/
- Snapshots are written atomically by Stable‑Baselines3
- Training and evaluation MUST run in separate processes

------------------------------------------------------------
5. Run a Trained Agent and Generate an Engine Replay
------------------------------------------------------------

Execute a trained PPO agent and record a state‑based engine replay.

Command:

python -c "from assault_runner.rl_runner import RLRunner
RLRunner().run_episode(
    model_path='models/ppo_level7_p4_2v2_roles',
    scenario_id='mettete_i_piedi_terra_1_min',
    output_path='replays/sample_engine_replay.json',
    deterministic=False
)"

Notes:
- deterministic=False enables stochastic policy execution
- Output is a snapshot‑per‑activation engine replay
- Engine replays must not be modified

------------------------------------------------------------
6. Visualize Engine Replay (Python Viewer)
------------------------------------------------------------

Change to the viewer scripts directory:

cd assault-viewer/scripts

Run the viewer:

python replay_viewer.py ..\..\replays\sample_engine_replay.json

Viewer capabilities:

- Hex‑grid terrain rendering
- Unit counters and stacking
- Camera pan and zoom
- Step‑by‑step deterministic playback

------------------------------------------------------------
7. Convert Engine Replay to Web Replay Format
------------------------------------------------------------

Convert an engine replay to the event‑based web format:

python scripts/convert_replay_to_web.py replays/sample_engine_replay.json assault-web/data/replay_demo.json

Notes:
- Conversion is offline and deterministic
- Events are inferred from engine state transitions
- Original engine replay remains unchanged

------------------------------------------------------------
8. Open the Web Replay Viewer
------------------------------------------------------------

Open:

assault-web/index.html

Use a local static HTTP server if required by the browser.

Web viewer capabilities:

- Forward / backward playback
- Unit movement history
- Active unit highlighting
- Basis for tactical explanations

------------------------------------------------------------
9. Offline Batch Evaluation and Engine Diagnostics
------------------------------------------------------------

This is the canonical offline evaluation system.
It replaces the old rollout‑based statistics pipeline.

Capabilities:

- Load PPO models offline from disk
- Execute 50 / 100 / N complete games
- RL vs heuristic
- Count wins, losses, and draws
- Collect structured engine diagnostics
- Save selected replays
- Detect tactical bottlenecks and engine regressions

------------------------------------------------------------
9.1 Analysis Modes: Benchmark vs Evaluation
------------------------------------------------------------

Offline analysis supports two distinct analysis modes.

Benchmark Mode (default)

Purpose:
- Regression testing
- Stability verification
- Detecting engine or policy breakage

Semantics:
- Deterministic policy execution
- Fixed random seed
- Fully reproducible outcomes

Interpretation:
- Answers the question:
  “Does a deterministic winning trajectory still exist?”
- A 100 percent win rate is expected and correct if such a trajectory exists

Evaluation Mode

Purpose:
- Competitive performance measurement
- Robustness assessment
- Heuristic validation

Semantics:
- Stochastic policy execution
- Per‑episode seed variation
- Non‑deterministic outcomes

Interpretation:
- Answers the question:
  “With what probability does the RL agent win against the heuristic?”

------------------------------------------------------------
9.2 Offline Analysis Command (Canonical)
------------------------------------------------------------

Benchmark mode (deterministic):

python -m assault_runner.analysis.offline_series_orchestrator
  --scenario mettete_i_piedi_terra_1_min
  --episodes 100
  --mode benchmark
  --save-replays 5
  --output results/run_benchmark

Evaluation mode (stochastic):

python -m assault_runner.analysis.offline_series_orchestrator --scenario mettete_i_piedi_terra_1_min --episodes 100 --mode evaluation --save-replays 5 --output results/run_evaluationpython -m assault_runner.analysis.offline_series_orchestrator --scenario mettete_i_piedi_terra_1_min --episodes 100 --mode evaluation --save-replays 5 --output results/run_evaluation

Optional debug output:

--debug

------------------------------------------------------------
10. Typical Workflow Summary
------------------------------------------------------------

1. Train the RL agent continuously
2. Run offline benchmark after refactors or engine changes
3. Run offline evaluation to assess real competitiveness
4. Inspect series_summary.json
5. Analyze engine diagnostics
6. Visualize selected replays
7. Adjust heuristics, rewards, or rules if needed
8. Repeat

------------------------------------------------------------
11. Source of Truth
------------------------------------------------------------

This file is the authoritative reference for:

- documentation build and publication
- training and running RL agents
- replay generation and visualization
- offline batch evaluation
- engine diagnostics and debugging workflows

No other document supersedes this file.