# Backend Architecture State

## Current structure (after cleanup)

- `assault_backend/main.py`
  - FastAPI app bootstrap
  - game/session endpoints
  - router registration
- `assault_backend/routers/rag.py`
  - RAG Copilot endpoints:
    - `POST /api/rag/query`
    - `POST /api/rag/explain_action`
    - `POST /api/rag/recommend_actions`
    - `POST /api/rag/training_analysis`
- `assault_backend/schemas/rag_copilot.py`
  - request models for copilot endpoints
- `assault_backend/services/*`
  - domain services (scenario/unit/action/map/targeting/SB3)
- `assault_backend/engine.py`, `hrl_service.py`, `tactical_service.py`
  - explainability orchestration layer

## RAG runtime modules

- `assault_rag/copilot/index_builder.py`
- `assault_rag/copilot/retriever.py`
- `assault_rag/copilot/services.py`

These are now the active modules behind the new RAG Copilot API.

RAG ingestion timing:
- `game_data_index` preload is executed at backend startup (`@app.on_event("startup")` in `assault_backend/main.py`).
- `rules_index` is also loaded at startup to warm the runtime path and reduce first-query latency.
- If preload fails, backend still boots for game frontend; RAG issues are logged and isolated.

## Cleanup applied

- Removed generated metric artifacts from backend root:
  - `assault_backend/metrics.csv`
  - `assault_backend/metrics_report_20260604T*.json`

This keeps backend source directory focused on executable code.

## Recommended next incremental cleanup

1. Split game endpoints from `main.py` into `routers/game.py`.
2. Split legacy explain endpoint (`/api/explain/activation`) into `routers/explain.py`.
3. Centralize all schemas in:
   - `schemas/explain.py`
   - `schemas/rag_copilot.py`
   - `schemas/game.py`
4. Keep `main.py` as composition root only (app + middleware + include routers).
