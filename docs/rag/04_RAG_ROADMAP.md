# RAG Copilot Roadmap

## Phases

- Phase A: product contract and MVP boundaries.
- Phase B: indexing pipelines (`rules_index`, `game_data_index`).
- Phase C: hybrid retrieval and evidence fusion.
- Phase D: short explainability endpoint.
- Phase E: live recommendation endpoint (advisory mode).
- Phase F: UI integration (Q&A, explain, recommend).
- Phase G: training level-1 analysis (post-hoc only).
- Phase H: evaluation and hardening.

## Current Delivery (this implementation pass)

- Core copilot modules created:
  - index builder,
  - hybrid retriever,
  - service layer for query/explain/recommend/training-analysis.
- Backend endpoints added for all four capabilities.
- Documentation baseline added under `docs/rag`.

## Next Milestones

1. Add deterministic regression tests for each endpoint.
2. Connect UI panel and add response rendering with citations.
3. Build golden dataset and nightly evaluation gate.
4. Add confidence calibration and better ranking quality.

## Main Risks

- Data/rules mismatch if source files drift.
- Weak retrieval ranking on ambiguous prompts.
- Overconfident advice without enough evidence.

## Mitigations

- Always expose limitations.
- Keep citations mandatory.
- Add golden tests and periodic source-sync checks.
