Behavioral Statistics
=====================

The behavior statistics module extracts **quantitative summaries**
from Replay data.

Purpose
-------

It answers the question:

**What does the agent do?**

This module focuses on *execution*, not intention.

---

Metrics Extracted
-----------------

Typical statistics include:

- action frequency distribution
- movement vs attack ratios
- idle vs active turns
- directionality biases
- engagement frequency
- temporal patterns across episodes

All metrics are derived directly from Replay content.

---

Inputs
------

- one or more Replay files

---

Outputs
-------

- structured statistics (counts, ratios)
- intermediate analysis artifacts
- data suitable for aggregation or visualization

---

Design Principles
-----------------

- replay‑driven
- deterministic
- policy‑agnostic
- RL‑agnostic
- offline only

This module does NOT interpret rationales.