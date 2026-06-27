# RAG KB Ingestion Workflow (Rulebook)

This workflow standardizes how to populate and maintain
`RAG_KB_RULEBOOK_EXPLICATIVO.md`.

## 1) Extract

- Parse chapter/section text from:
  - `docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf`
- Preserve chapter and subsection references (`9.10.3`, `10.9.6`, etc.).

## 2) Normalize

- Convert prose into atomic rules:
  - prerequisites
  - steps
  - prohibitions
  - edge_cases
- Keep wording simple and deterministic.

## 3) Link

- Map each chunk to:
  - implementation refs (`assault_model/*`, `assault_sim/*`)
  - test refs (`assault_model/tests/*`, `assault_sim/tests/*`)
  - status from roadmap vocabulary.

## 4) Validate

- Check no duplicate `id`.
- Check each chunk has `source_ref`.
- Check each implemented/partial chunk has at least one code ref.

## 5) Publish

- Update:
  - `docs/game_rules/ROADMAP_RULES_COVERAGE.md`
  - `docs/game_rules/annexes/B_PDF_TRACEABILITY.md`
- Add changelog note with timestamp and coverage delta.

## Suggested Increment Plan

- Pass A: chapters `6`, `8`, `9`.
- Pass B: chapters `10`, `11`.
- Pass C: chapters `12`, `13`.
- Pass D: examples/exceptions and "illegal action" explainer chunks.
