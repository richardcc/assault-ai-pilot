# Gap Analysis (Vendor vs Implemented vs Pending)

This page tracks convergence between canonical vendor rules and current code.

## Global Validation State

Current documentation pack status: **Pending Validation**.

Closure criteria:

- canonical PDF values transcribed,
- code mappings verified,
- test references completed,
- reviewer approval recorded.

## Priority Legend

- **High**: can change gameplay outcomes or training signals.
- **Medium**: affects fidelity, UX consistency, or edge-case correctness.
- **Low**: documentation, tooling, or non-critical optional parity.

## Current Gaps

| Area | Vendor Expectation | Current Status | Priority | Next Action |
| --- | --- | --- | --- | --- |
| Dice modifier parity (ranged + close combat) | Exact modifier tables and resolution order | Validation framework added in Annex C, canonical values pending transcription | High | Transcribe all chapter 10/11 modifier values and link tests |
| Full chapter-by-chapter parity | 100% mechanics from core + aids + clarifications | Core implemented, some rule edges not explicitly table-traced in code docs | High | Build per-section checklist (rule ID -> module -> test) |
| TAS/OAS edge coverage | Full support including rare branch cases | Main flow present, edge matrix not fully regression-tested | High | Add scenario tests for each TAS/OAS branch |
| Campaign persistence depth | Full campaign lifecycle and branch outcomes | Base structure documented, full parity audit pending | Medium | Add campaign outcome mapping tests |
| Optional FoW completeness | Complete optional module behavior | Feature documented, implementation selective | Medium | Gate + progressive enablement plan with tests |
| Traceability granularity | Direct PDF paragraph to code mapping | Chapter-level mapping available, paragraph-level pending | Medium | Add fine-grain trace table in annex |
| Documentation depth | Implementable spec without assumptions | Improved, still evolving toward exhaustive per-subsection detail | High | Expand chapter subsections with explicit pseudo-rules |

## Backlog Integration

Roadmap should keep these recurring tasks:

1. maintain per-rule trace table,
2. close high-priority parity gaps first,
3. require tests for any claim of "implemented".
