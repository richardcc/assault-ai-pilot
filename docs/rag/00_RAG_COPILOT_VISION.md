# RAG Copilot Vision

## Product Goal

`Nuevo RAG Assault` is an internal tactical copilot with four capabilities:

1. Rules/data Q&A (`/api/rag/query`)
2. AI action explainability (`/api/rag/explain_action`)
3. Live advisory recommendations (`/api/rag/recommend_actions`)
4. Training analysis Level 1 (`/api/rag/training_analysis`)

The system is designed to be **evidence-first**:
- cite sources,
- separate facts from inferences,
- return explicit limitations when evidence is missing.

## MVP Scope

- Rules + canonical game-data retrieval (units/scenarios/tables).
- Short explainability responses for tactical actions.
- Top-N advisory recommendations during gameplay (no auto-execution).
- Post-run training reports with detected tactical patterns and actionable suggestions.

## Non-Goals (MVP)

- Automatic execution of recommended actions.
- Online policy control in training/inference loops.
- Fully autonomous balancing/tuning.

## Success Criteria

- Golden-set questions resolved with citations.
- Explainability endpoint returns short, grounded rationale.
- Recommendation endpoint returns ranked actions with risk notes.
- Training analysis returns pattern detection + evidence-backed recommendations.
