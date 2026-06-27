# RAG Operations and Evaluation

## Reindex Procedure

Game-data index is generated lazily when the retriever runs, but can be built explicitly by importing:

- `assault_rag/copilot/index_builder.py`
- function `ensure_game_data_chunks()`

Expected output:
- `assault_rag/data/game_data/chunks/game_data_chunks.json`

## Operational Checklist

1. Verify canonical sources exist:
   - `assault_sim/assets/catalogs/unit_catalog.json`
   - `assault_sim/assets/scenarios/*.json`
2. Verify rulebook source exists:
   - `assault_rag/data/rulebook/chunks/rulebook_chunks.json` (or typed fallback)
3. Run backend and hit:
   - `/api/rag/query`
   - `/api/rag/explain_action`
   - `/api/rag/recommend_actions`
   - `/api/rag/training_analysis`
4. Confirm responses include `citations` and explicit `limitations` when needed.

## Evaluation Set (Golden Tests)

Maintain a small golden set for each capability:

- Query:
  - rules-only,
  - data-only,
  - hybrid.
- Explain action:
  - move decision,
  - ranged decision,
  - fallback decision.
- Recommend actions:
  - objective-pressure situation,
  - threat-heavy situation.
- Training level-1:
  - high wait ratio case,
  - low capture case,
  - low damage case.

## Acceptance Gates

- No endpoint returns empty answer without limitation.
- Citations present for evidence-backed responses.
- Recommendation mode remains advisory-only.
- Training analysis does not write back into policy/online control flow.
