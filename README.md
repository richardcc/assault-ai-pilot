---
title: Assault MLOps Dashboard & Replay Viewer
emoji: ⚔️
colorFrom: indigo
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# Assault MLOps Platform & Tactical Replay Viewer

Assault is an advanced multi-agent tactical decision-making platform powered by **EfficientZero V2** reinforcement learning, deterministic simulation, and comprehensive MLOps observability.

---

## 🚀 Live Services Included

- **MLOps Dashboard & Analytics Hub**
  - High-performance DuckDB & Parquet metric queries.
  - Multi-scenario ELO rating progression and breakthrough transfer lineage.
  - Sub-curriculum phase tracking and tactical loss curves (Value, Policy, Threat Map, Attrition, Morale).
- **Tactical Replay Viewer & Explainability**
  - Interactive hex-grid battlefield playback with step-by-step state inspection.
  - Tactical heads visualization: Threat Heatmap, Attrition Risk, and Morale Dynamics.
  - Action attribution and causal sitrep diagnostics.
- **Canonical Documentation Hub**
  - Full technical specifications, mathematical foundations, and evolutionary roadmap accessible at `/docs/`.

---

## 🛠️ Architecture & Tech Stack

- **Model Engine**: EfficientZero V2 (`agents/efficientzero_v2/`) with Two-hot Value/Reward, Spatial Attention, and PCGrad multi-task optimization.
- **Backend**: Native Python HTTP / DuckDB / PyArrow / Polars service (`mlops/reporting/viewer.py`).
- **Frontend**: React + Vite + Tailwind CSS single-page application (`mlops/reporting/viewer_frontend/`).
- **Data Engine**: DuckDB zero-copy analytics over telemetry Parquet tables (`runs_curriculum/experiments/reporting/`).

---

## 📦 Local Deployment

To run the complete platform locally:

```bash
# Start the reporting viewer on port 8778 (or custom port via PORT env variable)
python -m mlops.reporting.viewer --port 8778 --host 0.0.0.0
```

Access the interface in your browser:
- **MLOps Dashboard**: `http://localhost:8778`
- **Documentation Hub**: `http://localhost:8778/docs/`
