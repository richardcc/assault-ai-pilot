# assault-ai-pilot

Educational AI pilot for tactical decision-making under uncertainty,
focused on emergent coordination and **soft role allocation (SRT)**
in multi-unit environments.

---

## Overview

This project explores how reinforcement learning agents trained with
**Proximal Policy Optimization (PPO)** behave in increasingly complex
tactical scenarios under partial and symmetric information.

Rather than relying on reward shaping or explicit role assignment, the
system is designed to observe **emergent behavior** arising solely from
environment structure, information availability, and learning dynamics.

---

## Project Structure

The project is composed of four main components:

- **assault-env**  
  A Gym-compatible environment exposing tactical decision-making problems
  with deterministic dynamics and sequential unit activation.

- **assault-engine**  
  A fully deterministic game engine with strict separation between
  mechanics, rules, state, and execution.

- **assault-runner**  
  Training and evaluation utilities, including replay generation from
  trained policies.

- **assault-viewer**  
  A graphical replay viewer supporting hex-grid maps, layered terrain,
  camera control, and step-by-step visualization.

---

## Curriculum Summary

Training follows a staged curriculum in which exactly one source of
complexity is introduced at each phase:

- **P1** – Single-unit tactical control
- **P2** – Multi-unit interaction without global context (reveals a
  degenerate evasion local optimum)
- **P3** – Multi-unit interaction with global force awareness
- **P4** – Symmetric 2 vs 2 strategic engagement
- **P4-B** – Exploratory analysis of emergent *soft role allocation* (SRT)

The curriculum is designed to isolate causal factors and enable
interpretable learning dynamics.

---

## Documentation

Authoritative technical documentation is maintained using **Sphinx** and
is available in the `docs/` directory.

The documentation covers:

- Engine architecture and determinism
- Curriculum design and training results
- Emergent soft role allocation (SRT)
- Replay format and graphical viewer
- Hex-grid map rendering and design constraints

---

## Project Status

✅ Core engine and environment: **Stable**  
✅ PPO training pipeline: **Validated**  
✅ Replay generation and viewer: **Operational**  
✅ Emergent behavior analysis (SRT): **Concluded**

The project is currently in a **documentation and consolidation phase**.

---

## Notes

This repository is intended for educational and research purposes.