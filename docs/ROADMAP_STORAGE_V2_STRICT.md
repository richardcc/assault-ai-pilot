# ROADMAP_STORAGE_V2_STRICT

Status: **Closed (GO)**
Owner: MLOps + Reporting
Scope: End-to-end storage and consumption redesign for `models + evals + replay` focused on viewer performance.

## 1) Purpose and Governance

This roadmap defines the mandatory cutover plan to Storage/API v2 for viewer workloads.

This document is the governing source for cutover decisions:
- go/no-go criteria,
- hard cutover checklist,
- data-loss validation,
- latency acceptance.

No production cutover is allowed outside this roadmap.

## 2) Non-Negotiable Principles (Producer-Only Strict)

1. **Zero fallback**  
   No runtime fallback to alternative fields, legacy files, or inferred values in consumer/viewer.

2. **Zero legacy**  
   Legacy schemas and compatibility adapters are removed from the serving path after cutover.

3. **Zero frontend invention**  
   Frontend never synthesizes metrics, labels, or replay states not emitted by producer pipelines.

4. **Everything rendered comes from producer**  
   Every rendered datum must be traceable to producer-emitted artifacts (`raw`, `indexed`, or serving API output).

5. **Fail closed, not open**  
   Missing required producer fields must produce explicit `Unavailable`/error states, never silent defaults.

6. **Contract-first evolution**  
   Any field or semantic change starts in producer contract/versioning and is validated before UI exposure.

## 2.1 Common Producer-Consumer Contract (Mandatory)

This section is a hard requirement for Storage/API v2 cutover between Producer (Eval pipeline) and Consumer (WebUI/viewer).

1. **Single versioned shared schema**
   - Producer and consumer MUST use one shared versioned contract for payload structure and field semantics.
   - Contract version is exposed in manifest/API and validated before render paths are enabled.

2. **Single field/channel dictionary**
   - One authoritative dictionary defines each channel/field: type, required/nullable state, units, and missing-value semantics.
   - Dictionary includes canonical naming and payload placement (raw/indexed/serving) to avoid drift.

3. **Producer-owned provenance and availability flags**
   - `*_source` and `*_available` fields are defined and emitted by producer contracts.
   - Viewer consumes these fields as-is; interpretation logic must not rewrite or infer alternative provenance/availability values.

4. **No frontend reconstruction**
   - Frontend is forbidden from reconstructing missing producer fields, synthesizing derived contract fields, or backfilling legacy aliases.
   - If required fields are missing, viewer must fail closed with explicit `Unavailable`/error semantics.

Validation state: **Validated (GO, 2026-07-21)**.

## 2.2 Technical Governance Mechanism (Contract Enforcement)

1. **Single contract artifact**
   - Maintain one JSON Schema/contract package used by both writer (producer/index pipeline/API serializer) and reader (viewer/client parser).
   - Contract package is the only source for required/optional/nullability and channel semantics.

2. **Bidirectional contract tests**
   - Producer contract tests assert "producer emits contract-compliant payloads".
   - Consumer contract tests assert "consumer reads only emitted fields and fails closed on missing required fields".

3. **CI contract gate (mandatory)**
   - CI must fail if producer output breaks shared contract version/schema.
   - CI must fail if viewer expects fields not emitted by producer artifacts/API.
   - No release/cutover approval if any contract gate is red.

Validation state: **Validated (GO, 2026-07-21)**.

## 3) Target Architecture (Raw / Indexed / Serving)

## 3.1 Raw Layer (immutable ingest)

- Input artifacts are immutable, append-only, and content-addressed where applicable.
- Primary payloads:
  - replay event streams,
  - evaluation episode summaries,
  - model metadata and checkpoints,
  - run/manifests metadata.
- Raw artifacts are never edited in place.

## 3.2 Indexed Layer (query-optimized derived data)

- Deterministic batch/index jobs convert raw artifacts into query-efficient datasets.
- Indexed outputs are reproducible from raw + job version + manifest.
- Indexes include:
  - catalog slices for fast listing/filtering,
  - replay timeline indexes,
  - metric projection tables for viewer tabs.
- Indexed layer is the only allowed source for high-cardinality viewer queries.

## 3.3 Serving Layer (strict API v2)

- A single API v2 serves viewer data from indexed artifacts and manifests.
- API v2 enforces:
  - strict schema contracts,
  - explicit versioning,
  - required/optional field semantics,
  - no legacy compatibility transformation.
- Viewer consumes only API v2 endpoints and schemas.

## 3.4 Producer-Driven Catalog Publication (Train + Eval)

- Catalog publication is producer-owned and mandatory:
  - train completion must publish/update model/train catalog entries,
  - eval completion must publish/update eval/episode/index entries.
- Viewer/runtime must never rebuild canonical catalog state from ad-hoc filesystem scans during normal serving.
- Catalog/index updates must be atomic (publish-on-success) and versioned with schema v2.
- If publication fails, run status must be explicit (`incomplete_catalog_publication`) and serving must fail closed for missing required entries.

Validation state: **Validated (GO, 2026-07-21)**.

## 4) Artifact Formats and Layer Baseline

This section defines the explicit high-performance storage baseline for Storage/API v2.

## 4.1 Recommended format by layer

- **Raw replay/events**: NDJSON compressed with zstd (`*.ndjson.zst`).
- **Catalogs/summaries/analytic tables (indexed layer)**: Parquet.
- **Small metadata/control plane**: JSON manifest.
- **Optional local serving layer for developer workflows**: DuckDB or SQLite materialization from indexed artifacts.

## 4.2 Rationale and trade-offs

### NDJSON + zstd (raw replay/events)

Why:
- append-friendly and stream-friendly for producer emitters,
- easy deterministic ordering and line-level traceability during reconciliation,
- zstd significantly reduces storage and IO for long replay timelines.

Trade-offs:
- row-oriented scans are slower for large analytic aggregations than columnar formats,
- requires decompression during read and careful chunking for random access.

### Parquet (catalog/summaries/analytics)

Why:
- columnar layout improves projection/filter performance for viewer and benchmark queries,
- strong typed schema and encoding/partition support for deterministic indexed outputs,
- efficient for high-cardinality metrics and large table retrieval workloads.

Trade-offs:
- less convenient for append-only per-event logging,
- schema evolution must be managed strictly to avoid drift across producers/jobs.

### JSON manifest (small metadata/control)

Why:
- human-readable contract anchor for versions, checksums, completeness and references,
- low operational complexity for orchestration and validation tooling.

Trade-offs:
- not optimized for large analytical reads,
- must remain small and authoritative (metadata only, never replay payload substitute).

### DuckDB or SQLite (optional local serving)

Why:
- practical local/offline serving cache for developer diagnostics and reproducible investigations,
- fast embedded query engine without requiring external service dependencies.

Trade-offs:
- extra materialization step from indexed artifacts,
- optional convenience layer only; not a replacement for producer contracts or API v2 strictness.

## 4.3 Project baseline decision (recommended)

Baseline decision for this project:
1. Raw producer output uses **NDJSON + zstd**.
2. Indexed/viewer analytical outputs use **Parquet**.
3. Control/integrity metadata uses **JSON manifests**.
4. **DuckDB** is the primary local serving/query layer for catalog/model history APIs, with SQLite as optional fallback for constrained environments.

Validation state: **Validated (GO, 2026-07-21)**.

## 4.4 Strict policy guardrails for formats

- No fallback to legacy JSON blobs for replay/catalog serving once cutover is complete.
- No dual-path runtime readers that silently switch format.
- No frontend format inference or synthetic field reconstruction.
- Any new format introduction requires contract/version update, reconciliation tests, and roadmap/go-no-go approval.

## 5) API Contract v2 (Strict)

## 5.1 Contract policy

- Versioned namespace: `/api/v2/...`
- Breaking changes require new minor/major contract release with migration plan in producer.
- Unknown fields are ignored only if contract marks them as `extensible`; required fields are strict.
- No v1 fallback routes in viewer runtime.

## 5.2 Required endpoint families

1. **Catalog**
   - list runs/models/evals with pagination and server-side filters.
2. **Replay**
   - replay timeline and per-step decision payloads from indexed source.
3. **Metrics**
   - precomputed aggregates and distributions needed by viewer tabs.
4. **Manifest/Health**
   - contract/schema version exposure and data completeness status.

## 5.3 Error semantics

- `400`: invalid query/contract violation from consumer input.
- `409`: version or manifest incompatibility.
- `422`: requested data exists but is incomplete for strict render contract.
- `5xx`: backend/infra failures.

No endpoint may return synthetic placeholder payloads that look valid.

## 6) Phased Execution Plan

## P0 - Contract Freeze and Inventory

Objective: freeze v2 producer contract and map all required viewer fields.

Deliverables:
- canonical schema definitions (raw/indexed/serving),
- common producer-consumer JSON Schema package version `v2.x` created and published,
- single field/channel dictionary with type + required/nullable + units + missing semantics,
- producer field inventory per viewer surface,
- strict required/optional matrix,
- manifest spec v2,
- format policy freeze: NDJSON+zstd (raw), Parquet (indexed), JSON manifest (control), optional DuckDB/SQLite (local only).

Exit criteria:
- contract reviewed and approved by producer + viewer owners,
- all viewer-rendered fields mapped to producer sources,
- `*_source` and `*_available` definitions approved in shared dictionary and manifest/API exposure,
- explicit "no frontend reconstruction" policy accepted by viewer owners,
- unresolved fields tracked as blockers (not silently assumed).

## P1 - Producer and Index Pipeline Build

Objective: emit v2-compliant raw artifacts and deterministic indexed datasets.

Deliverables:
- producer emitters for NDJSON/Parquet/manifest v2,
- producer emits shared contract fields including canonical `*_source` and `*_available`,
- train/eval post-run publishers write canonical catalog/index updates as part of completion contract,
- zstd compression/decompression standards for raw replay/events and validation tooling,
- index jobs with reproducibility metadata,
- data quality checks (schema + completeness + checksum),
- producer contract test suite (positive/negative) wired to CI gate.

Exit criteria:
- full pipeline run produces v2 artifacts for representative workloads,
- parity checks against expected source totals pass,
- producer contract tests pass for all required endpoints/artifacts,
- strict validation reports generated and stored.

## P2 - Serving API v2 and Viewer Wiring

Objective: expose strict API v2 and connect viewer without legacy paths.

Deliverables:
- API v2 endpoints for catalog/replay/metrics/manifest,
- Parquet-backed query path as default serving source for catalog/metrics and indexed replay timeline retrieval,
- viewer integration using only `/api/v2`,
- removal of runtime catalog reconstruction path in viewer-serving (except explicit offline debug mode),
- explicit fail-closed rendering states for missing required producer data,
- viewer reads shared contract package and field dictionary without local field invention/reconstruction,
- consumer contract test suite (reads emitted fields only; fails on missing required fields) wired to CI gate.

Exit criteria:
- no viewer runtime dependency on v1/legacy contracts,
- replay and catalog flows operate end-to-end on v2 artifacts,
- consumer contract tests pass against producer-emitted fixtures and API v2 payloads,
- CI confirms viewer does not request non-emitted contract fields,
- latency SLO verification executed (see section 9).

## P3 - Hard Cutover and Legacy Removal

Objective: perform irreversible cutover to strict v2 and remove legacy serving.

Deliverables:
- go/no-go signoff package,
- production cutover execution,
- legacy path decommission checklist complete,
- explicit verification that runtime fallback/legacy JSON serving paths are removed or disabled,
- contract-governance evidence pack: shared schema version tag, bidirectional test reports, and green CI contract gate history.

Exit criteria:
- all go-live checklist gates pass,
- no critical regressions in first monitoring window,
- producer-consumer common contract is the only active runtime contract with no frontend field reconstruction paths,
- rollback window policy closed according to release governance.

## 7) Hard Cutover Checklist (Go/No-Go)

All checks are mandatory. Any failed check is automatic **NO-GO**.

1. Contract v2 is frozen and tagged.
2. Producer emits required fields with zero critical schema violations.
3. Indexed datasets are complete and checksum-validated.
4. API v2 passes strict contract tests (positive + negative cases).
5. Viewer uses only v2 endpoints in runtime configuration.
6. No legacy/fallback code path enabled in serving or frontend.
6.b Train/eval producer publication hooks are active and are the only source of canonical catalog/index updates.
7. Shared producer-consumer schema package version is pinned and validated in producer + consumer builds.
8. CI contract gate is green: producer emits contract-compliant payloads and viewer expects only emitted fields.
9. `*_source` and `*_available` semantics are producer-defined and consumed as-is by viewer.
10. No frontend reconstruction/synthesis of contract fields is present in runtime code paths.
11. Data-loss validation suite passes (section 8).
12. Latency acceptance criteria pass for catalog and replay (section 9).
13. Operational runbook updated for v2 incidents and recovery.
14. Signoff recorded by producer owner, viewer owner, and release owner.

Go-live location: this section is the authoritative cutover gate list.

## 8) Data-Loss Validation (No Loss Policy)

Validation must prove no silent loss across raw -> indexed -> serving.

Required validations:
1. **Count reconciliation**
   - event/episode/run totals match expected baselines by partition.
2. **Key integrity**
   - unique keys preserved (`run_id`, `episode_id`, `step_idx` where applicable).
3. **Field completeness**
   - required fields have no missing values beyond declared nullable contract.
4. **Semantic reconciliation**
   - sampled replay timelines match producer source events exactly in order and values.
5. **Manifest integrity**
   - checksums and artifact references resolve and verify.

Acceptance:
- zero unresolved critical mismatches,
- documented exceptions only if approved as explicit contract updates (never implicit).

## 9) Latency Acceptance Criteria (Catalog and Replay)

All latencies measured server-side and end-to-end viewer request paths.

## 9.1 Catalog latency gates

- `p50 <= 300 ms`
- `p95 <= 900 ms`
- `p99 <= 1500 ms`

Test conditions:
- representative production-like index size,
- concurrent read load profile agreed by platform + viewer.

## 9.2 Replay latency gates

- replay header/metadata fetch `p95 <= 1200 ms`
- first timeline page `p95 <= 1800 ms`
- timeline pagination step `p95 <= 900 ms`

Test conditions:
- long-episode and high-event-density scenarios included,
- cold and warm cache runs both reported.

Any gate breach is **NO-GO** until corrected and revalidated.

## 10) Responsibilities Matrix

- **Producer team**: schema governance, artifact emission, manifest integrity.
- **Indexing team**: deterministic transforms, performance indexes, reconciliation checks.
- **Serving team**: API v2 strict contract enforcement and latency compliance.
- **Viewer team**: zero-invention consumption and fail-closed UX.
- **Release owner**: go/no-go orchestration and cutover evidence archive.

## 11) Validation Status

Current state: **Closed (GO, 2026-07-21)**

Closure evidence (executed 2026-07-21):
- strict smoke train+eval completed (`scripts/run_smoke_train_eval_v2_catalog.ps1`),
- producer-driven post-run catalog publication confirmed (train + eval hooks active),
- strict runtime behavior confirmed (no hot catalog reconstruction fallback),
- targeted test suites green:
  - `mlops/tests/test_contracts_v2.py` + `mlops/tests/test_storage_v2.py`,
  - `mlops/tests/test_catalog_publisher_v2.py` + `mlops/tests/test_reporting_viewer_catalog_loading.py`,
  - `mlops/tests/test_reporting_catalog.py` + `mlops/tests/test_reporting_viewer_api_v2.py`,
  - `mlops/tests/test_reporting_viewer_replay_filter.py`.

## 12) Viewer Refactor Program (Decompose viewer.py)

Status: **Validated (structural refactor delivered)**
Owner: Reporting + MLOps
Scope: structured decomposition of `mlops/reporting/viewer.py` without changing strict producer-first behavior.

### 12.1 Technical motivation

- `viewer.py` is currently monolithic and concentrates catalog loading, replay assembly, state handling, rendering, and diagnostics in one large module.
- Monolith coupling increases maintenance cost, slows onboarding, and makes targeted fixes risky because behavior changes are hard to isolate.
- Regression risk is elevated: edits in one concern can silently impact unrelated tabs/workflows due to shared implicit state.
- Testability is constrained: unit tests are coarse-grained, and many scenarios require heavy integration setup instead of focused module tests.

### 12.2 Target modular architecture

Target decomposition (logical package boundaries):

1. **Catalog/Data Adapters**
   - catalog schema parsing, normalization, strict contract guards, and typed accessors.
2. **Replay Loader**
   - replay fetch/load/index flow, timeline slicing, and producer-traceable replay payload assembly.
3. **State Store**
   - immutable/controlled viewer state transitions, filter/sort/search state, and selected run/step pointers.
4. **Render Helpers**
   - reusable formatting, value rendering policies, strict `Unavailable` presentation helpers.
5. **Tab Modules**
   - per-tab composition and view logic (overview, metrics, replay, decision influence, diagnostics).
6. **Diagnostics Modules**
   - decision diagnostics parsing, anomaly flags, and explanation panes backed only by producer fields.

### 12.3 Phased plan (P0-P3)

#### P0 - Baseline and boundaries

Deliverables:
- dependency/call graph snapshot for current `viewer.py`,
- module-boundary map with import direction rules,
- strict contract checklist for each extracted concern,
- no-behavior-change baseline golden outputs for representative viewer scenarios.

#### P1 - Core extraction

Deliverables:
- `catalog/data adapters`, `replay loader`, and `state store` extracted into dedicated modules,
- `viewer.py` converted into orchestration/composition entrypoint,
- focused unit tests for extracted modules (contract parsing, replay loading, state transitions),
- compatibility shims limited to internal imports only (no runtime fallback behavior).

#### P2 - UI composition extraction

Deliverables:
- `render helpers`, `tab modules`, and `diagnostics modules` extracted,
- tab-level test coverage for rendering/diagnostic paths with producer-origin fixtures,
- explicit strict fail-closed behavior retained (`Unavailable`/error where required fields are missing),
- UX parity checklist completed for key workflows (catalog -> replay -> diagnostics).

#### P3 - Hardening and cleanup

Deliverables:
- dead-code and duplicate-helper removal from legacy monolith,
- import-cycle checks and module-size guardrails enforced in CI,
- regression suite pass across benchmark/reporting workflows,
- final architecture notes and ownership map published in docs.

### 12.4 Acceptance criteria

1. **Module size guardrail**
   - no extracted module exceeds 500 LOC (excluding tests), and orchestration `viewer.py` target is <= 300 LOC.
2. **Test coverage**
   - >= 85% line coverage for new adapter/loader/state/render helper modules,
   - mandatory regression tests for catalog loading, replay filtering, diagnostics rendering, and strict `Unavailable` states.
3. **No UX regression**
   - key user flows preserve behavior and output semantics relative to baseline snapshots,
   - no increase in critical viewer errors for benchmark smoke datasets.
4. **Strict-policy compliance**
   - no fallback to legacy fields, no frontend metric invention, no synthetic provenance;
   - all rendered values remain producer-traceable and fail closed when required fields are absent.

### 12.5 Strict policy compatibility

This refactor is structural only and must remain fully compatible with section 2 strict policy:
- zero fallback,
- zero legacy serving path dependence,
- zero frontend invention,
- producer-first traceability and fail-closed semantics.

Any refactor change that alters field semantics or introduces inferred frontend data is **NO-GO** until contract governance review and validation evidence are updated.

## 13) Post-GO Implementation Snapshot (2026-07-21)

Delivered after formal GO closure:

- Producer publication now emits:
  - slim operational catalog (`model_catalog_latest.json`),
  - full debug catalog (`model_catalog_full_latest.json`),
  - parquet indexes (`catalog_models.parquet`, `catalog_evals.parquet`, `catalog_trains.parquet`),
  - DuckDB materialization (`reporting.duckdb`).
- API v2 now runs index/database-first for key flows:
  - `/api/v2/catalog` -> DuckDB primary (JSON fallback explicit),
  - `/api/v2/model` -> index-first detail assembly,
  - `/api/v2/model/evals` -> parquet-first pagination,
  - `/api/v2/model/trains` -> DuckDB-first pagination.
- Runtime catalog fallback reconstruction remains disabled in strict mode.
- Legacy bench summary file (`runs/bench_latest.json`) is removed from runtime write path (no write, no opt-in toggle).
- Operational gates added:
  - persistence/performance gate (`mlops/reporting/perf_gate.py`),
  - unified go/no-go script (`scripts/gate_reporting_v2_go_nogo.ps1`).

## 14) Post-Closure Backlog (Non-Blocking, Ordered)

1. **Incremental publication/index updates (phase 2, optimization)**  
   Phase 1 implemented (Parquet upsert merge mode for `catalog_models/evals/trains`). Remaining: true per-run delta ingestion without full catalog scan/build.

2. **Retention and compaction policy (phase 2, optimization)**  
   Phase 1 is implemented (debug full catalog history pruning with keep-N). Remaining: retention policy for eval bundles and long-tail replay artifacts.

3. **Legacy endpoint retirement (completed)**  
   Legacy routes (`/api/catalog`, `/api/model`) are now retired (HTTP 410) and no longer re-enabled via runtime flags. Added operational status endpoint: `/api/v2/publish-status`.

4. **Performance SLO hard gates in CI (completion)**  
   Local perf gate and unified go/no-go are implemented. Remaining: wire these scripts into CI and persist trend history.

5. **DuckDB coverage expansion**  
   Complete migration of `/api/v2/model` detail enrichment away from per-file JSON reads (`run_manifest`, `bench_eval`) into DuckDB-indexed views/materialized tables.

6. **Failure-recovery hardening (phase 2, optimization)**  
   Phase 1 implemented (`catalog_publish_status.json`, phase markers, partial/failed status). Added one-shot repair runner (`scripts/repair_catalog_publication_v2.ps1`) + go/no-go auto-retry. Remaining: scheduled/daemonized auto-repair and multi-attempt backoff policy.

## 15) Formal Closure

Roadmap closure decision: **CLOSED (GO)**.

Closure basis:
- strict producer-consumer contract and fail-closed behavior validated,
- producer-driven publication active for train/eval with atomic publish + status traceability,
- runtime serving migrated to v2 index/database-first paths (Parquet + DuckDB),
- legacy catalog/model endpoints retired,
- operational gates available (`perf_gate`, unified `go/no-go`) and passing in target environment.

Remaining items in section 14 are explicitly **post-closure optimizations** and do not block roadmap closure.
