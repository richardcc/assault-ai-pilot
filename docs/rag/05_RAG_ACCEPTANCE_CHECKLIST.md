# RAG MVP Acceptance Checklist

## Automated checks

- [x] Golden endpoint tests exist:
  - `assault_backend/tests/test_rag_copilot_endpoints.py`
- [x] Quick execution script exists:
  - `scripts/ptest_rag_copilot.ps1`

## Endpoint coverage

- [x] `POST /api/rag/query`
  - Response shape validated (`mode`, `answer`, `citations`, `evidence`, `limitations`)
- [x] `POST /api/rag/explain_action`
  - Response shape validated (`short_explanation`, `citations`, `limitations`)
- [x] `POST /api/rag/recommend_actions`
  - Response shape validated (`recommendations`, rationale/risk/citations, `limitations`)
- [x] `POST /api/rag/training_analysis`
  - Response shape validated (`patterns`, `metrics`, `examples`, `recommendations`, `citations`, `limitations`)

## MVP functional acceptance (manual runtime)

- [ ] Run:
  - `python -m pytest assault_backend/tests/test_rag_copilot_endpoints.py -q`
  - or `./scripts/ptest_rag_copilot.ps1`
- [ ] Verify backend runtime returns citations when evidence exists.
- [ ] Verify limitation path is explicit when evidence is missing.
- [ ] Verify recommendation endpoint is advisory-only (no action execution side effects).
- [ ] Verify training analysis remains post-hoc (no online policy intervention).

## Notes

- In this environment, shell execution sometimes reports `no exit status`; if that occurs,
  run the script locally in your terminal to confirm green tests.
