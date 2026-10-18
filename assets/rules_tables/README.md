# Rules Tables Canonical Assets

This directory is the canonical location for static gameplay tables used by:

- the simulation engine, and
- the RAG explainability layer.

## Convention

- Keep tables versioned (`*.v1.json`, `*.v2.json`, ...).
- Add/update `manifest/rules_tables_manifest.v1.json` whenever a table changes.
- Prefer data-driven tables here over hardcoded constants in Python modules.

## Intended Subfolders

- `terrain/`
- `fortification/`
- `combat/`
- `los/`
- `movement/`
- `manifest/`
