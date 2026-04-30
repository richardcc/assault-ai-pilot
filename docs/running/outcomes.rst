Episode and Series Outcomes
===========================

Outcome computation defines **how the result of a match is determined**
and how results are aggregated across multiple games.

In the Assault‑Env project, outcomes are intentionally derived from
**final engine state only**, without reference to learning signals,
intermediate rewards or policy internals.

This design ensures that outcome statistics reflect **what happened in
the game**, not how the agent was trained.

Episode outcomes
----------------

Each completed match produces a single **episode outcome**.

An episode outcome consists of:

- The winning side (Side A, Side B, or Draw)
- Final victory point totals for each side
- Total number of turns executed

Episode outcomes are computed **only once per match**, after the engine
reaches a terminal state.

No intermediate information is considered when determining the result.

Outcome determination
---------------------

Victory and draw conditions are defined entirely by the tactical engine.

The outcome computation layer:

- Reads the final engine state
- Applies engine‑defined win conditions
- Records the result in a structured format

This guarantees that:

- All agents are evaluated using identical criteria
- Outcome semantics are independent of the learning algorithm
- No evaluation logic is duplicated or reinterpreted elsewhere

Series‑level aggregation
------------------------

When multiple matches are executed as a batch, individual episode
outcomes are aggregated into **series‑level statistics**.

The series aggregation process records:

- Number of wins for each side
- Number of draws
- Total number of games executed

From these counts, normalized rates are derived, such as:

- Win rates per side
- Draw rate

Normalization allows meaningful comparison between experimental runs
with different batch sizes.

Relation to diagnostics
-----------------------

Outcome statistics are intentionally **kept separate** from engine
diagnostics.

Outcome data answers questions such as:

- Which side won more often?
- How frequently do matches end in draws?
- How consistent are results across runs?

Diagnostics answer orthogonal questions, such as:

- What opportunities were available?
- What risks dominated the tactical space?
- Which actions were avoided or taken?

This separation prevents outcome metrics from obscuring
structural or behavioral explanations.

Interpretation boundaries
-------------------------

Outcome statistics do **not** attempt to explain *why* a result occurred.

They are:

- Descriptive
- Non‑causal
- Non‑interpretive

Causal explanations and behavioral interpretations are derived only by
**combining outcomes with diagnostics and replay inspection**.

Persistence and reproducibility
--------------------------------

Episode outcomes and aggregated series results are persisted as
structured JSON files.

These artifacts are:

- Immutable once written
- Independent of training state
- Human‑ and machine‑readable

Because outcomes depend only on final engine state, they can be
recomputed and verified at any time by replaying the corresponding
matches.

Summary
-------

The outcome system provides a minimal, unambiguous definition of
win, loss and draw conditions.

By restricting outcome computation to final engine state and keeping it
separate from diagnostics and learning processes, the system ensures
that performance statistics remain **robust, comparable and
reproducible** across experiments.
